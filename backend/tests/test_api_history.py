"""API 端到端：历史方案不可变 + 只标不修 + 新方案按现网约束分岔。

用内存 sqlite + 依赖覆盖，不依赖 postgres。
"""
import json
import os

import pytest

os.environ.setdefault("DATABASE_URL", "sqlite://")  # 必须在导入 app.* 之前

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import app.database as db_mod
from app.database import Base, get_db
from app.models.models import Candidate, Hall, PaperSet, SeatPlan


@pytest.fixture()
def client():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    TestingSession = sessionmaker(bind=engine, autoflush=False)
    Base.metadata.create_all(engine)
    db_mod.engine = engine
    db_mod.SessionLocal = TestingSession

    from app.main import app

    def _override():
        s = TestingSession()
        try:
            yield s
        finally:
            s.close()

    app.dependency_overrides[get_db] = _override
    # 直接造数据，不触发生命周期里的 postgres create_all/seed
    s = TestingSession()
    hall = Hall(code="H101", name="一号考室", rows=5, cols=6, min_manhattan=2, blocked_seats="[]")
    s.add(hall)
    s.flush()
    p1 = PaperSet(code="P-A", title="A卷")
    p2 = PaperSet(code="P-B", title="B卷")
    s.add_all([p1, p2])
    s.flush()
    for i in range(8):
        s.add(Candidate(hall_id=hall.id, name=f"C{i}", ticket_no=f"T{i}",
                        paper_id=p1.id if i % 2 == 0 else p2.id))
    s.commit()
    s.close()

    # 不使用 with，避免触发 lifespan（postgres）
    c = TestClient(app)
    yield c, TestingSession
    app.dependency_overrides.clear()


def test_history_immutable_and_drift_after_min_dist_change(client):
    c, Session = client

    # 1) 种子先排一版（min_dist=2）
    r = c.post("/api/seating/run", json={"hall_id": 1})
    assert r.status_code == 200
    plan_a = r.json()
    id_a = plan_a["id"]
    seats_a = {a["candidate_id"]: [a["row"], a["col"]] for a in plan_a["assignments"]}
    viols_a = plan_a["violations"]
    raw_a_before = Session().get(SeatPlan, id_a).result_json

    # 2) 后来改最小距 2 → 3（现网约束）
    r = c.patch("/api/halls/1", json={"min_manhattan": 3})
    assert r.status_code == 200 and r.json()["min_manhattan"] == 3

    # 3) 打开历史：座位与违规钉在生成当时
    r = c.get(f"/api/seating/plan/{id_a}")
    assert r.status_code == 200
    hist = r.json()
    assert {a["candidate_id"]: [a["row"], a["col"]] for a in hist["assignments"]} == seats_a
    assert hist["violations"] == viols_a
    assert hist["stats"] == plan_a["stats"]

    # 4) 只亮漂移标记，不悄悄重排
    assert hist["drift"]["drifted"] is True
    assert hist["drift"]["counts"].get("distance", 0) >= 1
    assert hist["constraint_diff"]["min_manhattan"] == {"stored": 2, "current": 3, "changed": True}

    # 5) 禁止为让历史变绿改库：库里的旧 result_json 必须逐字节不变
    raw_a_after = Session().get(SeatPlan, id_a).result_json
    assert raw_a_after == raw_a_before
    assert json.loads(raw_a_after).get("drift") is None  # 漂移绝不入库

    # 6) 历史列表仍只有 1 个方案（GET 不得新增/重排）
    plans = c.get("/api/seating/plans?hall_id=1").json()["plans"]
    assert [p["id"] for p in plans] == [id_a]

    # 7) 新点排座按新距出新图
    r = c.post("/api/seating/run", json={"hall_id": 1})
    plan_b = r.json()
    id_b = plan_b["id"]
    assert id_b != id_a
    seats_b = {a["candidate_id"]: (a["row"], a["col"]) for a in plan_b["assignments"]}
    # 新图满足新距
    coords = list(seats_b.values())
    for i, x in enumerate(coords):
        for y in coords[i + 1:]:
            assert abs(x[0] - y[0]) + abs(x[1] - y[1]) >= 3
    assert plan_b["violations"] == []

    # 8) 两套数字分岔同时成立：旧座位没变成新座位
    hist_again = c.get(f"/api/seating/plan/{id_a}").json()
    assert {a["candidate_id"]: [a["row"], a["col"]] for a in hist_again["assignments"]} == seats_a
    assert {a["candidate_id"]: [a["row"], a["col"]] for a in hist_again["assignments"]} != seats_b


def test_blocked_and_paper_drift(client):
    c, Session = client
    plan = c.post("/api/seating/run", json={"hall_id": 1}).json()
    pid = plan["id"]
    # 找一个历史固定座位与一个考生
    a0 = plan["assignments"][0]
    seat = [a0["row"], a0["col"]]
    cand_id = a0["candidate_id"]
    # 该考生原来的套别
    old_paper = a0["paper_id"]
    other_paper = next(p["id"] for p in c.get("/api/papers").json() if p["id"] != old_paper)

    # 设禁坐格 + 换套别（都只改现网）
    assert c.patch("/api/halls/1", json={"blocked_seats": [seat]}).status_code == 200
    assert c.patch(f"/api/candidates/{cand_id}", json={"paper_id": other_paper}).status_code == 200

    hist = c.get(f"/api/seating/plan/{pid}").json()
    kinds = {i["kind"] for i in hist["drift"]["items"]}
    assert "seat_blocked" in kinds
    assert "paper_changed" in kinds
    # 座位仍在原地（含禁坐格上）——只标不修
    again = [a for a in hist["assignments"] if a["candidate_id"] == cand_id][0]
    assert [again["row"], again["col"]] == seat
    # 违规仍是冻结原文，不含漂移
    assert all(v["kind"] not in {"seat_blocked", "paper_changed"} for v in hist["violations"])


def test_violations_endpoint_separates_frozen_and_drift(client):
    c, _ = client
    plan = c.post("/api/seating/run", json={"hall_id": 1}).json()
    c.patch("/api/halls/1", json={"min_manhattan": 4})
    res = c.get(f"/api/seating/violations?plan_id={plan['id']}").json()
    assert res["violations"] == plan["violations"]  # 冻结
    assert res["drift"]["drifted"] is True           # 漂移另起一节
