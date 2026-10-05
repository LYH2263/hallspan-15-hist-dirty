"""Exam seating engine.

不可变历史原则（与 place_candidates / evaluate_drift 的分工）：

- ``place_candidates`` + ``find_violations`` 只在**生成新方案**时按现网约束执行，
  结果连同 constraints 快照一起落库，之后再不改写。
- ``evaluate_drift`` 对历史方案的**固定座位**做只读评估：拿现网约束（最小距、
  禁坐格、现行套别）去比对，只产出漂移标记，绝不移动座位、不改写结果。
  「只标不修」——历史变绿只能来自按现网约束重新排一张新图，而不是重排旧图。
"""
from __future__ import annotations

from collections import Counter
from dataclasses import asdict, dataclass

ENGINE_VERSION = 2


@dataclass
class SeatAssign:
    candidate_id: int
    name: str
    ticket_no: str
    paper_id: int
    row: int
    col: int


@dataclass
class Violation:
    kind: str
    a_id: int
    b_id: int
    detail: str


def manhattan(a: tuple[int, int], b: tuple[int, int]) -> int:
    return abs(a[0] - b[0]) + abs(a[1] - b[1])


def neighbors4(r: int, c: int, rows: int, cols: int) -> list[tuple[int, int]]:
    out = []
    for dr, dc in ((0, 1), (0, -1), (1, 0), (-1, 0)):
        nr, nc = r + dr, c + dc
        if 0 <= nr < rows and 0 <= nc < cols:
            out.append((nr, nc))
    return out


def parse_blocked(blocked: object, rows: int | None = None, cols: int | None = None) -> set[tuple[int, int]]:
    """归一化禁坐格。接受 ["0,1", "2,3"]、[[0, 1], [2, 3]]、{(0, 1)} 等形式。

    给出 rows/cols 时丢弃越界坐标（现网网格内的才有效）。
    """
    out: set[tuple[int, int]] = set()
    if not blocked:
        return out
    for item in blocked:
        if isinstance(item, str):
            r_s, _, c_s = item.partition(",")
            r, c = int(r_s), int(c_s)
        else:
            r, c = int(item[0]), int(item[1])
        if rows is not None and cols is not None and not (0 <= r < rows and 0 <= c < cols):
            continue
        out.add((r, c))
    return out


def place_candidates(
    rows: int,
    cols: int,
    min_dist: int,
    candidates: list[dict],
    blocked_seats: object = None,
) -> tuple[list[SeatAssign], list[dict]]:
    """按现网约束贪心排座：行序找座，跳过禁坐格；

    接受条件：与所有已排者曼哈顿距离 >= min_dist，且不与同套四邻相邻。
    """
    blocked = parse_blocked(blocked_seats, rows, cols)
    occupied: dict[tuple[int, int], SeatAssign] = {}
    unplaced: list[dict] = []
    for cand in candidates:
        placed = False
        for r in range(rows):
            for c in range(cols):
                if (r, c) in occupied or (r, c) in blocked:
                    continue
                ok = True
                for pos, other in occupied.items():
                    if manhattan((r, c), pos) < min_dist:
                        ok = False
                        break
                    if other.paper_id == cand["paper_id"] and (r, c) in neighbors4(pos[0], pos[1], rows, cols):
                        ok = False
                        break
                if not ok:
                    continue
                for nr, nc in neighbors4(r, c, rows, cols):
                    if (nr, nc) in occupied and occupied[(nr, nc)].paper_id == cand["paper_id"]:
                        ok = False
                        break
                if not ok:
                    continue
                assign = SeatAssign(cand["id"], cand["name"], cand["ticket_no"], cand["paper_id"], r, c)
                occupied[(r, c)] = assign
                placed = True
                break
            if placed:
                break
        if not placed:
            unplaced.append(cand)
    return list(occupied.values()), unplaced


def find_violations(rows: int, cols: int, min_dist: int, assigns: list[SeatAssign]) -> list[Violation]:
    """按**生成当时**的约束计算违规——结果冻结入库，打开历史时原样回放。"""
    viols: list[Violation] = []
    for i, a in enumerate(assigns):
        for b in assigns[i + 1:]:
            d = manhattan((a.row, a.col), (b.row, b.col))
            if d < min_dist:
                viols.append(Violation("distance", a.candidate_id, b.candidate_id,
                                       f"曼哈顿距离 {d} < 最小要求 {min_dist}"))
            if a.paper_id == b.paper_id and (b.row, b.col) in neighbors4(a.row, a.col, rows, cols):
                viols.append(Violation("same_paper_adjacent", a.candidate_id, b.candidate_id,
                                       f"同试卷套 {a.paper_id} 四邻相邻"))
    return viols


def evaluate_drift(
    rows: int,
    cols: int,
    current_min_dist: int,
    assigns: list[SeatAssign],
    current_paper_by_candidate: dict[int, int],
    current_blocked: object,
) -> dict:
    """只读漂移评估：用**现网约束**检查历史**固定座位**，只标记不重排。

    - distance：现网最小距收紧后，固定座位间距离不再达标；
    - same_paper_adjacent：按考生**现行套别**，固定座位四邻撞同套；
    - seat_blocked：固定座位后来被设为禁坐格；
    - paper_changed：考生套别于排座之后被改动（元数据漂移，座位不动）。

    不修改 ``assigns``，不返回任何新座位布局。
    """
    items: list[dict] = []
    involved: set[int] = set()
    cur_pid = dict(current_paper_by_candidate or {})
    blocked = parse_blocked(current_blocked, rows, cols)

    def add(kind: str, a_id: int, b_id: int | None, detail: str) -> None:
        items.append({"kind": kind, "a_id": a_id, "b_id": b_id, "detail": detail})
        involved.add(a_id)
        if b_id is not None:
            involved.add(b_id)

    # 1/2：逐对检查距离与现行套别四邻（坐标固定，取历史快照网格）
    for i, a in enumerate(assigns):
        for b in assigns[i + 1:]:
            d = manhattan((a.row, a.col), (b.row, b.col))
            if d < current_min_dist:
                add("distance", a.candidate_id, b.candidate_id,
                    f"现网最小距 {current_min_dist}，固定座位实际 {d}（历史只读，仅标记不重排）")
            pa, pb = cur_pid.get(a.candidate_id), cur_pid.get(b.candidate_id)
            if (
                pa is not None and pa == pb
                and (b.row, b.col) in neighbors4(a.row, a.col, rows, cols)
            ):
                add("same_paper_adjacent", a.candidate_id, b.candidate_id,
                    f"按现行套别 {pa}，两人固定座位四邻相邻（历史只读，仅标记不重排）")

    # 3：固定座位落入现网禁坐
    for a in assigns:
        if (a.row, a.col) in blocked:
            add("seat_blocked", a.candidate_id, None,
                f"固定座位 ({a.row},{a.col}) 后来被设为禁坐（历史只读，仅标记不重排）")

    # 4：套别于排座后被改动
    for a in assigns:
        cur = cur_pid.get(a.candidate_id)
        if cur is not None and cur != a.paper_id:
            add("paper_changed", a.candidate_id, None,
                f"套别变更：排座时 {a.paper_id} → 现行 {cur}（历史座位不动）")

    counts = dict(Counter(x["kind"] for x in items))
    return {
        "drifted": bool(items),
        "items": items,
        "involved_candidate_ids": sorted(involved),
        "counts": counts,
    }


def make_constraints_snapshot(min_dist: int, blocked: set[tuple[int, int]]) -> dict:
    return {
        "min_manhattan": min_dist,
        "blocked_seats": [list(p) for p in sorted(blocked)],
    }


def plan_to_dict(assigns: list[SeatAssign], unplaced: list[dict], viols: list[Violation],
                 rows: int, cols: int, constraints: dict) -> dict:
    return {
        "version": ENGINE_VERSION,
        "rows": rows,
        "cols": cols,
        "constraints": constraints,
        "assignments": [asdict(a) for a in assigns],
        "unplaced": unplaced,
        "violations": [asdict(v) for v in viols],
        "stats": {
            "seated": len(assigns),
            "unplaced": len(unplaced),
            "violations": len(viols),
            "capacity": rows * cols,
        },
    }
