import json
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.models import Candidate, Hall, SeatPlan
from app.services.seat_engine import (
    SeatAssign,
    evaluate_drift,
    find_violations,
    make_constraints_snapshot,
    parse_blocked,
    place_candidates,
    plan_to_dict,
)

router = APIRouter(prefix="/seating", tags=["seating"])


class RunIn(BaseModel):
    hall_id: int = 1


def _hydrate(assigns_raw: list[dict]) -> list[SeatAssign]:
    return [
        SeatAssign(
            candidate_id=a["candidate_id"],
            name=a.get("name", ""),
            ticket_no=a.get("ticket_no", ""),
            paper_id=a["paper_id"],
            row=a["row"],
            col=a["col"],
        )
        for a in assigns_raw
    ]


def _blocked_diff(stored: list, current: set[tuple[int, int]]) -> dict:
    old = {tuple(x) for x in (stored or [])}
    new = set(current)
    return {
        "added": [list(p) for p in sorted(new - old)],
        "removed": [list(p) for p in sorted(old - new)],
    }


def _attach_drift(data: dict, hall: Hall, db: Session) -> dict:
    """在**不改动存储结果**的前提下，用现网约束对冻结座位做只读漂移评估。

    历史方案的 assignments / violations / stats 一律原样返回；
    漂移只出现在响应里的 drift 与 constraint_diff 字段。
    """
    assigns = _hydrate(data.get("assignments", []))
    cand_ids = [a.candidate_id for a in assigns]
    current_paper = {
        c.id: c.paper_id
        for c in db.scalars(select(Candidate).where(Candidate.id.in_(cand_ids))).all()
    } if cand_ids else {}
    current_blocked = parse_blocked(json.loads(hall.blocked_seats or "[]"), hall.rows, hall.cols)

    data["drift"] = evaluate_drift(
        hall.rows, hall.cols, hall.min_manhattan, assigns, current_paper, current_blocked
    )
    stored_constraints = data.get("constraints")
    if stored_constraints is None:
        # 早于约束快照功能的老方案：漂移仍可实时算，但差异对比缺基线。
        data["constraint_diff"] = {"snapshot": None}
    else:
        data["constraint_diff"] = {
            "min_manhattan": {
                "stored": stored_constraints.get("min_manhattan"),
                "current": hall.min_manhattan,
                "changed": stored_constraints.get("min_manhattan") != hall.min_manhattan,
            },
            "blocked_seats": _blocked_diff(stored_constraints.get("blocked_seats", []), current_blocked),
        }
    return data


def _get_plan(plan_id: int, db: Session) -> SeatPlan:
    plan = db.get(SeatPlan, plan_id)
    if not plan:
        raise HTTPException(404, "历史方案不存在")
    return plan


def _latest_plan(hall_id: int, db: Session) -> SeatPlan | None:
    return db.scalars(
        select(SeatPlan).where(SeatPlan.hall_id == hall_id).order_by(SeatPlan.id.desc())
    ).first()


def _serialize(plan: SeatPlan, hall: Hall, db: Session) -> dict:
    data = json.loads(plan.result_json)
    data = _attach_drift(data, hall, db)
    return {"id": plan.id, "hall_id": plan.hall_id, "created_at": plan.created_at.isoformat(), **data}


@router.post("/run")
def run_seating(body: RunIn | None = None, db: Session = Depends(get_db)):
    """按**现网**约束（现行最小距/禁坐格/现行套别）排一张**新**图。

    只 INSERT 新快照，绝不 UPDATE 任何历史方案。
    """
    hall_id = body.hall_id if body else 1
    hall = db.get(Hall, hall_id)
    if not hall:
        raise HTTPException(404, "考室不存在")
    blocked = parse_blocked(json.loads(hall.blocked_seats or "[]"), hall.rows, hall.cols)
    cands = [
        {"id": c.id, "name": c.name, "ticket_no": c.ticket_no, "paper_id": c.paper_id}
        for c in db.scalars(select(Candidate).where(Candidate.hall_id == hall_id)).all()
    ]
    assigns, unplaced = place_candidates(hall.rows, hall.cols, hall.min_manhattan, cands, blocked)
    viols = find_violations(hall.rows, hall.cols, hall.min_manhattan, assigns)
    result = plan_to_dict(
        assigns, unplaced, viols, hall.rows, hall.cols,
        make_constraints_snapshot(hall.min_manhattan, blocked),
    )
    result["hall"] = {"id": hall.id, "name": hall.name, "min_manhattan": hall.min_manhattan}
    plan = SeatPlan(hall_id=hall_id, created_at=datetime.utcnow(),
                    result_json=json.dumps(result, ensure_ascii=False))
    db.add(plan)
    db.commit()
    db.refresh(plan)
    return _serialize(plan, hall, db)


@router.get("/plans")
def list_plans(hall_id: int = 1, db: Session = Depends(get_db)):
    """历史方案索引（只给摘要，座位/违规在详情里取冻结原文）。"""
    plans = db.scalars(
        select(SeatPlan).where(SeatPlan.hall_id == hall_id).order_by(SeatPlan.id.desc())
    ).all()
    out = []
    for p in plans:
        d = json.loads(p.result_json)
        out.append({
            "id": p.id,
            "created_at": p.created_at.isoformat(),
            "constraints": d.get("constraints"),
            "stats": d.get("stats"),
        })
    return {"hall_id": hall_id, "plans": out}


@router.get("/plan/{plan_id}")
def get_plan(plan_id: int, db: Session = Depends(get_db)):
    """打开历史：座位与违规原样回放，只额外挂漂移标记（只标不修）。"""
    plan = _get_plan(plan_id, db)
    hall = db.get(Hall, plan.hall_id)
    if not hall:
        raise HTTPException(404, "考室不存在")
    return _serialize(plan, hall, db)


@router.get("/latest")
def latest(hall_id: int = 1, db: Session = Depends(get_db)):
    plan = _latest_plan(hall_id, db)
    if not plan:
        raise HTTPException(404, "尚无排座方案，请按现网约束执行排座")
    hall = db.get(Hall, hall_id)
    return _serialize(plan, hall, db)


@router.get("/violations")
def violations(plan_id: int | None = None, hall_id: int = 1, db: Session = Depends(get_db)):
    """冻结违规（生成当时算出、原样存储）+ 现网漂移，分两节返回，互不覆盖。"""
    plan = _get_plan(plan_id, db) if plan_id else _latest_plan(hall_id, db)
    if not plan:
        raise HTTPException(404, "尚无排座方案")
    hall = db.get(Hall, plan.hall_id)
    data = _serialize(plan, hall, db)
    return {
        "plan_id": plan.id,
        "hall_id": plan.hall_id,
        "violations": data.get("violations", []),
        "unplaced": data.get("unplaced", []),
        "drift": data.get("drift", {}),
        "constraint_diff": data.get("constraint_diff", {}),
    }


@router.get("/stats")
def stats(plan_id: int | None = None, hall_id: int = 1, db: Session = Depends(get_db)):
    plan = _get_plan(plan_id, db) if plan_id else _latest_plan(hall_id, db)
    if not plan:
        raise HTTPException(404, "尚无排座方案")
    hall = db.get(Hall, plan.hall_id)
    data = _serialize(plan, hall, db)
    return {
        "plan_id": plan.id,
        "hall_id": plan.hall_id,
        **data.get("stats", {}),
        "drift_count": len(data.get("drift", {}).get("items", [])),
    }
