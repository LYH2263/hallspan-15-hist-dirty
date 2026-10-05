import json
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.models import Candidate, Hall, SeatPlan
from app.services.drift import compute_drift, parse_blocked, snapshot_constraints, snapshot_from_plan
from app.services.seat_engine import find_violations, place_candidates, plan_to_dict

router = APIRouter(prefix="/seating", tags=["seating"])


def _hall_or_404(db: Session, hall_id: int) -> Hall:
    hall = db.get(Hall, hall_id)
    if not hall:
        raise HTTPException(404, "考室不存在")
    return hall


def _candidates(db: Session, hall_id: int) -> list[Candidate]:
    return db.scalars(select(Candidate).where(Candidate.hall_id == hall_id).order_by(Candidate.id)).all()


def _plan_payload(plan: SeatPlan, hall: Hall, candidates: list[Candidate]) -> dict:
    """历史方案响应：座位/违规原样返回存盘快照，漂移标记现场派生（只标不修）。"""
    result = json.loads(plan.result_json)
    snapshot = snapshot_from_plan(plan)
    return {
        "id": plan.id,
        "hall_id": plan.hall_id,
        "created_at": plan.created_at.isoformat() if plan.created_at else None,
        **result,
        "constraints": snapshot,
        "drift": compute_drift(snapshot, hall, candidates),
    }


@router.post("/run")
def run_seating(hall_id: int = 1, db: Session = Depends(get_db)):
    """按现网约束生成新方案（新插一行，绝不改写已有方案）。"""
    hall = _hall_or_404(db, hall_id)
    cands = _candidates(db, hall_id)
    blocked = parse_blocked(hall.blocked_seats)
    engine_cands = [{"id": c.id, "name": c.name, "ticket_no": c.ticket_no, "paper_id": c.paper_id}
                    for c in cands]
    assigns, unplaced = place_candidates(hall.rows, hall.cols, hall.min_manhattan, engine_cands, blocked)
    viols = find_violations(hall.rows, hall.cols, hall.min_manhattan, assigns)
    result = plan_to_dict(assigns, unplaced, viols, hall.rows, hall.cols, blocked)
    result["hall"] = {"id": hall.id, "name": hall.name, "min_manhattan": hall.min_manhattan}
    snapshot = snapshot_constraints(hall, cands)
    plan = SeatPlan(hall_id=hall_id, created_at=datetime.utcnow(),
                    result_json=json.dumps(result, ensure_ascii=False),
                    constraints_json=json.dumps(snapshot, ensure_ascii=False))
    db.add(plan)
    db.commit()
    db.refresh(plan)
    return _plan_payload(plan, hall, cands)


@router.get("/plans")
def list_plans(hall_id: int = 1, db: Session = Depends(get_db)):
    """历史方案清单（新的在前），供只读回看。"""
    plans = db.scalars(select(SeatPlan).where(SeatPlan.hall_id == hall_id)
                       .order_by(SeatPlan.id.desc())).all()
    out = []
    for p in plans:
        result = json.loads(p.result_json)
        snap = snapshot_from_plan(p)
        out.append({
            "id": p.id,
            "hall_id": p.hall_id,
            "created_at": p.created_at.isoformat() if p.created_at else None,
            "min_manhattan": snap.get("min_manhattan"),
            "stats": result.get("stats", {}),
        })
    return out


@router.get("/plans/{plan_id}")
def get_plan(plan_id: int, db: Session = Depends(get_db)):
    """打开历史方案：返回钉在生成当时的座位与违规 + 相对现网约束的漂移标记。"""
    plan = db.get(SeatPlan, plan_id)
    if not plan:
        raise HTTPException(404, "方案不存在")
    hall = _hall_or_404(db, plan.hall_id)
    return _plan_payload(plan, hall, _candidates(db, plan.hall_id))


@router.get("/latest")
def latest(hall_id: int = 1, db: Session = Depends(get_db)):
    plan = db.scalars(select(SeatPlan).where(SeatPlan.hall_id == hall_id)
                      .order_by(SeatPlan.id.desc())).first()
    if not plan:
        return run_seating(hall_id=hall_id, db=db)
    hall = _hall_or_404(db, hall_id)
    return _plan_payload(plan, hall, _candidates(db, hall_id))


@router.get("/violations")
def violations(hall_id: int = 1, plan_id: int | None = None, db: Session = Depends(get_db)):
    data = get_plan(plan_id, db) if plan_id is not None else latest(hall_id=hall_id, db=db)
    return {"hall_id": data["hall_id"], "plan_id": data["id"],
            "violations": data.get("violations", []), "unplaced": data.get("unplaced", []),
            "drift": data.get("drift")}


@router.get("/stats")
def stats(hall_id: int = 1, plan_id: int | None = None, db: Session = Depends(get_db)):
    data = get_plan(plan_id, db) if plan_id is not None else latest(hall_id=hall_id, db=db)
    return {"hall_id": data["hall_id"], "plan_id": data["id"],
            "created_at": data.get("created_at"), **data.get("stats", {})}
