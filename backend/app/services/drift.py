"""约束快照与漂移检测。

不变量：
- 历史方案的座位与违规钉在生成当时（SeatPlan.result_json 一旦写入不再改）。
- 现网约束（最小距 / 禁坐 / 套别）与历史不一致时，只计算漂移标记返回给前端展示，
  绝不回写、不重排历史方案 —— 只标不修。
"""
from __future__ import annotations

import json


def parse_blocked(raw: str | None) -> list[list[int]]:
    """把 Hall.blocked_seats 文本解析成 [[r, c], ...]，容错返回空表。"""
    try:
        data = json.loads(raw or "[]")
    except ValueError:
        return []
    out = []
    for p in data if isinstance(data, list) else []:
        if isinstance(p, (list, tuple)) and len(p) == 2:
            out.append([int(p[0]), int(p[1])])
    return out


def snapshot_constraints(hall, candidates) -> dict:
    """生成当时的约束快照，随方案一次性写入 constraints_json。"""
    return {
        "min_manhattan": hall.min_manhattan,
        "blocked_seats": parse_blocked(hall.blocked_seats),
        "papers": {str(c.id): c.paper_id for c in candidates},
    }


def snapshot_from_plan(plan) -> dict:
    """读取方案存盘的约束快照；兼容没有 constraints_json 的旧方案（回退到 result_json）。"""
    try:
        snap = json.loads(plan.constraints_json or "{}")
    except ValueError:
        snap = {}
    if snap.get("min_manhattan") is not None:
        snap.setdefault("blocked_seats", [])
        snap.setdefault("papers", {})
        return snap
    result = json.loads(plan.result_json or "{}")
    hall = result.get("hall") or {}
    return {
        "min_manhattan": hall.get("min_manhattan"),
        "blocked_seats": result.get("blocked_seats") or [],
        "papers": {},
    }


def compute_drift(snapshot: dict, hall, candidates) -> dict:
    """对比方案快照与现网约束，输出漂移标记。纯派生计算，不落库。"""
    drift = {
        "has_drift": False,
        "min_manhattan": None,      # {"then": x, "now": y}
        "blocked_added": [],        # 快照后新增的禁坐格
        "blocked_removed": [],      # 快照后取消的禁坐格
        "paper_changes": [],        # 套别变更的考生
    }
    then_min = snapshot.get("min_manhattan")
    if then_min is not None and then_min != hall.min_manhattan:
        drift["min_manhattan"] = {"then": then_min, "now": hall.min_manhattan}

    then_blocked = {tuple(p) for p in (snapshot.get("blocked_seats") or [])}
    now_blocked = {tuple(p) for p in parse_blocked(hall.blocked_seats)}
    drift["blocked_added"] = sorted([list(p) for p in now_blocked - then_blocked])
    drift["blocked_removed"] = sorted([list(p) for p in then_blocked - now_blocked])

    then_papers = snapshot.get("papers") or {}
    for c in candidates:
        old = then_papers.get(str(c.id))
        if old is not None and old != c.paper_id:
            drift["paper_changes"].append({
                "candidate_id": c.id, "name": c.name, "ticket_no": c.ticket_no,
                "then": old, "now": c.paper_id,
            })

    if (drift["min_manhattan"] or drift["blocked_added"]
            or drift["blocked_removed"] or drift["paper_changes"]):
        drift["has_drift"] = True
    return drift
