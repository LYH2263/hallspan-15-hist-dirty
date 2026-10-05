from app.services.seat_engine import (
    SeatAssign,
    evaluate_drift,
    find_violations,
    manhattan,
    parse_blocked,
    place_candidates,
)


def test_manhattan():
    assert manhattan((0, 0), (2, 1)) == 3


def test_min_distance_placement():
    cands = [{"id": i, "name": f"C{i}", "ticket_no": f"T{i}", "paper_id": 1 + (i % 2)} for i in range(4)]
    assigns, unplaced = place_candidates(4, 4, 2, cands)
    assert len(assigns) + len(unplaced) == 4
    for i, a in enumerate(assigns):
        for b in assigns[i+1:]:
            assert manhattan((a.row, a.col), (b.row, b.col)) >= 2


def test_same_paper_not_adjacent_in_result():
    cands = [
        {"id": 1, "name": "A", "ticket_no": "T1", "paper_id": 1},
        {"id": 2, "name": "B", "ticket_no": "T2", "paper_id": 1},
        {"id": 3, "name": "C", "ticket_no": "T3", "paper_id": 2},
    ]
    assigns, _ = place_candidates(3, 3, 1, cands)
    viols = find_violations(3, 3, 1, assigns)
    assert not any(v.kind == "same_paper_adjacent" for v in viols)


def test_violation_detection():
    assigns = [
        SeatAssign(1, "A", "T1", 1, 0, 0),
        SeatAssign(2, "B", "T2", 1, 0, 1),
    ]
    viols = find_violations(2, 2, 2, assigns)
    kinds = {v.kind for v in viols}
    assert "distance" in kinds
    assert "same_paper_adjacent" in kinds


# ---------- 禁坐 ----------

def test_blocked_seats_never_used():
    blocked = [[r, c] for r in range(3) for c in range(3)]  # 全禁
    cands = [{"id": i, "name": f"C{i}", "ticket_no": f"T{i}", "paper_id": 1} for i in range(3)]
    assigns, unplaced = place_candidates(3, 3, 1, cands, blocked)
    assert assigns == [] and len(unplaced) == 3


def test_parse_blocked_formats_and_oob():
    assert parse_blocked(["0,1", [2, 3]]) == {(0, 1), (2, 3)}
    assert parse_blocked([[0, 0], [9, 9]], rows=3, cols=3) == {(0, 0)}


# ---------- 漂移：只标不修 ----------

def test_drift_distance_after_tightening_is_marked_not_repaired():
    # 历史固定座位：两人曼哈顿距离 2，在 min_dist=2 时合法无违规
    assigns = [
        SeatAssign(1, "A", "T1", 1, 0, 0),
        SeatAssign(2, "B", "T2", 2, 0, 2),
    ]
    paper_map = {1: 1, 2: 2}
    frozen_viols = find_violations(3, 6, 2, assigns)
    assert frozen_viols == []  # 冻结时无违规

    # 现网把最小距收到 3：只许亮漂移，不许动座位
    drift = evaluate_drift(3, 6, 3, assigns, paper_map, [])
    assert drift["drifted"] is True
    assert [i["kind"] for i in drift["items"]] == ["distance"]
    # 座位坐标钉死
    assert [(a.row, a.col) for a in assigns] == [(0, 0), (0, 2)]


def test_drift_seat_blocked_and_paper_changed():
    assigns = [
        SeatAssign(1, "A", "T1", 1, 0, 0),
        SeatAssign(2, "B", "T2", 2, 0, 2),
    ]
    # 现网：套别把 2 号也改成卷 1（不相邻，故无 same_paper_adjacent），(0,0) 设禁
    drift = evaluate_drift(3, 6, 2, assigns, {1: 1, 2: 1}, [[0, 0]])
    kinds = {i["kind"] for i in drift["items"]}
    assert kinds == {"seat_blocked", "paper_changed"}
    assert [(a.row, a.col) for a in assigns] == [(0, 0), (0, 2)]  # 仍不动


def test_drift_same_paper_after_paper_switch():
    assigns = [
        SeatAssign(1, "A", "T1", 1, 0, 0),
        SeatAssign(2, "B", "T2", 2, 0, 1),
    ]
    # 排座时不同套（故冻结违规里没有同卷相邻），现行套别都改成 1
    frozen = find_violations(3, 6, 1, assigns)
    assert not [v for v in frozen if v.kind == "same_paper_adjacent"]
    drift = evaluate_drift(3, 6, 1, assigns, {1: 1, 2: 1}, [])
    kinds = {i["kind"] for i in drift["items"]}
    # 换套：既亮 paper_changed 元数据漂移，也亮按现行套别的四邻漂移
    assert "same_paper_adjacent" in kinds
    assert "paper_changed" in kinds
    assert [(a.row, a.col) for a in assigns] == [(0, 0), (0, 1)]  # 座位不动


# ---------- 端到端分岔：先排一版 → 改最小距 → 旧方案不变亮漂移 → 新方案按新距 ----------

def _make_cands():
    return [{"id": i, "name": f"C{i}", "ticket_no": f"T{i}", "paper_id": 1 + (i % 2)}
            for i in range(8)]


def test_two_plans_diverge_after_min_dist_change():
    cands = _make_cands()

    # 第一版：min_dist=2
    assigns_v1, unplaced_v1 = place_candidates(5, 6, 2, cands)
    viols_v1 = find_violations(5, 6, 2, assigns_v1)
    seats_v1 = {a.candidate_id: (a.row, a.col) for a in assigns_v1}

    # 现网约束改成 3，拿旧固定座位评估漂移（只读）
    paper_map = {c["id"]: c["paper_id"] for c in cands}
    drift = evaluate_drift(5, 6, 3, assigns_v1, paper_map, [])

    # 第二版：按新距 3 出新图
    assigns_v2, unplaced_v2 = place_candidates(5, 6, 3, cands)
    seats_v2 = {a.candidate_id: (a.row, a.col) for a in assigns_v2}
    viols_v2 = find_violations(5, 6, 3, assigns_v2)

    # 旧数字不变（座位、违规冻结）
    assert {a.candidate_id: (a.row, a.col) for a in assigns_v1} == seats_v1
    assert len(viols_v1) == 0
    # 旧方案相对新距确实漂移（密度下必然有人距离 <3）
    assert drift["drifted"] is True
    assert drift["counts"].get("distance", 0) >= 1

    # 新方案满足新距
    for i, a in enumerate(assigns_v2):
        for b in assigns_v2[i+1:]:
            assert manhattan((a.row, a.col), (b.row, b.col)) >= 3
    assert len(viols_v2) == 0

    # 两套数字分岔同时成立：新图比旧图更稀疏（座位更少或布局不同）
    assert seats_v1 != seats_v2
    assert len(assigns_v2) <= len(assigns_v1)
    # 旧版座位仍是 min_dist=2 下的合法布局，没有被"后台变绿"
    assert len(unplaced_v1) == 0
