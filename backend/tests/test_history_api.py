"""历史方案只读 + 漂移只标不修 的验收测试。

种子场景：先排一版 → 改最小距 → 旧方案座位不变且亮漂移，新方案按新距出图，
两套数字分岔必须同时成立。
"""


def _run(client, hall_id=1):
    r = client.post(f"/api/seating/run?hall_id={hall_id}")
    assert r.status_code == 200, r.text
    return r.json()


def _get_plan(client, plan_id):
    r = client.get(f"/api/seating/plans/{plan_id}")
    assert r.status_code == 200, r.text
    return r.json()


def test_seed_scenario_min_distance_fork(client):
    # 1) 种子后排第一版（min=2）
    plan1 = _run(client)
    seats1 = plan1["assignments"]
    assert plan1["constraints"]["min_manhattan"] == 2
    assert plan1["drift"]["has_drift"] is False
    assert seats1, "首版应排出座位"

    # 2) 改现网最小距 2 → 3
    r = client.patch("/api/halls/1", json={"min_manhattan": 3})
    assert r.status_code == 200, r.text
    assert r.json()["min_manhattan"] == 3

    # 3) 旧方案钉在生成当时：座位、违规原样，只亮漂移标记
    old_view = _get_plan(client, plan1["id"])
    assert old_view["assignments"] == seats1
    assert old_view["violations"] == plan1["violations"]
    assert old_view["constraints"]["min_manhattan"] == 2
    assert old_view["drift"]["has_drift"] is True
    assert old_view["drift"]["min_manhattan"] == {"then": 2, "now": 3}

    # 4) 新点排座按现网约束出新图
    plan2 = _run(client)
    assert plan2["id"] != plan1["id"]
    assert plan2["constraints"]["min_manhattan"] == 3
    pos = [(a["row"], a["col"]) for a in plan2["assignments"]]
    for i, pa in enumerate(pos):
        for pb in pos[i + 1:]:
            assert abs(pa[0] - pb[0]) + abs(pa[1] - pb[1]) >= 3, "新方案必须满足新最小距"

    # 5) 两套数字分岔同时成立：旧方案仍是旧座位，清单里两版并存
    assert _get_plan(client, plan1["id"])["assignments"] == seats1
    plans = client.get("/api/seating/plans?hall_id=1").json()
    assert [p["id"] for p in plans] == [plan2["id"], plan1["id"]]
    assert plans[0]["min_manhattan"] == 3
    assert plans[1]["min_manhattan"] == 2


def test_history_violations_never_recomputed(client):
    """只标不修：旧约束下 0 违规的方案，改约束后仍显示旧违规（禁止后台重排变绿/变红）。"""
    plan1 = _run(client)
    assert plan1["violations"] == []  # 引擎在 min=2 下生成的方案自洽

    client.patch("/api/halls/1", json={"min_manhattan": 3})
    # 按新约束重算旧座位必然出现距离违规，但库内旧结果禁止被改写
    view = _get_plan(client, plan1["id"])
    assert view["violations"] == []
    assert view["drift"]["min_manhattan"] == {"then": 2, "now": 3}

    v = client.get(f"/api/seating/violations?plan_id={plan1['id']}").json()
    assert v["violations"] == []
    assert v["drift"]["has_drift"] is True


def test_blocked_seats_drift_and_new_plan(client):
    plan1 = _run(client)

    r = client.patch("/api/halls/1", json={"blocked_seats": [[0, 2], [1, 1]]})
    assert r.status_code == 200, r.text
    assert r.json()["blocked_seats"] == [[0, 2], [1, 1]]

    # 旧方案：座位钉住，亮禁坐漂移
    view = _get_plan(client, plan1["id"])
    assert view["assignments"] == plan1["assignments"]
    assert view["drift"]["blocked_added"] == [[0, 2], [1, 1]]
    assert view["drift"]["has_drift"] is True

    # 新方案：按现网禁坐出图，禁坐格不落人
    plan2 = _run(client)
    assert plan2["constraints"]["blocked_seats"] == [[0, 2], [1, 1]]
    assert plan2["blocked_seats"] == [[0, 2], [1, 1]]
    assert not any([a["row"], a["col"]] in [[0, 2], [1, 1]] for a in plan2["assignments"])

    # 取消禁坐 → 对 plan2 亮 blocked_removed
    client.patch("/api/halls/1", json={"blocked_seats": []})
    view2 = _get_plan(client, plan2["id"])
    assert view2["drift"]["blocked_removed"] == [[0, 2], [1, 1]]
    assert view2["assignments"] == plan2["assignments"]


def test_paper_change_drift(client):
    plan1 = _run(client)
    cid = plan1["assignments"][0]["candidate_id"]
    cands = client.get("/api/candidates").json()
    cur = next(c for c in cands if c["id"] == cid)
    new_paper = 2 if cur["paper_id"] != 2 else 1

    r = client.patch(f"/api/candidates/{cid}", json={"paper_id": new_paper})
    assert r.status_code == 200, r.text
    assert r.json()["paper_id"] == new_paper

    view = _get_plan(client, plan1["id"])
    changes = view["drift"]["paper_changes"]
    assert any(ch["candidate_id"] == cid and ch["then"] == cur["paper_id"] and ch["now"] == new_paper
               for ch in changes)
    assert view["drift"]["has_drift"] is True
    # 历史座位与违规仍钉住
    assert view["assignments"] == plan1["assignments"]
    assert view["violations"] == plan1["violations"]


def test_constraints_change_does_not_touch_stored_plans(client):
    """改约束前后直接读库：旧方案 result_json 字节级不变（禁止改库内旧结果）。"""
    from app.database import SessionLocal
    from app.models.models import SeatPlan
    from sqlalchemy import select

    plan1 = _run(client)
    db = SessionLocal()
    try:
        before = db.get(SeatPlan, plan1["id"]).result_json
    finally:
        db.close()

    client.patch("/api/halls/1", json={"min_manhattan": 4, "blocked_seats": [[0, 0]]})
    cands = client.get("/api/candidates").json()
    client.patch(f"/api/candidates/{cands[0]['id']}", json={"paper_id": 3})
    _run(client)  # 再排一版新的

    db = SessionLocal()
    try:
        after = db.get(SeatPlan, plan1["id"]).result_json
        count = len(db.scalars(select(SeatPlan)).all())
    finally:
        db.close()
    assert after == before, "历史方案存盘内容被改写，违反只读不变量"
    assert count == 2, "只能新增方案，不得更新旧方案"


def test_latest_does_not_auto_rerun(client):
    """打开页面（latest）不得悄悄重排：无方案时才生成首版。"""
    first = client.get("/api/seating/latest?hall_id=1").json()
    again = client.get("/api/seating/latest?hall_id=1").json()
    assert again["id"] == first["id"], "latest 不得隐式生成新方案"
    plans = client.get("/api/seating/plans?hall_id=1").json()
    assert len(plans) == 1


def test_legacy_plan_without_snapshot_falls_back(client):
    """没有 constraints_json 的旧方案：回退到 result_json 里的约束，仍可亮漂移。"""
    import json as _json
    from app.database import SessionLocal
    from app.models.models import SeatPlan

    plan1 = _run(client)
    db = SessionLocal()
    try:
        row = db.get(SeatPlan, plan1["id"])
        row.constraints_json = "{}"  # 模拟旧库遗留方案
        db.commit()
    finally:
        db.close()

    client.patch("/api/halls/1", json={"min_manhattan": 5})
    view = _get_plan(client, plan1["id"])
    assert view["constraints"]["min_manhattan"] == 2  # 从 result_json 的 hall 段回退
    assert view["drift"]["min_manhattan"] == {"then": 2, "now": 5}
    assert view["assignments"] == plan1["assignments"]
