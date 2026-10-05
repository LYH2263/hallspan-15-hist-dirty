from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.models import Hall
from app.services.seat_engine import parse_blocked
import json

router = APIRouter(prefix="/halls", tags=["halls"])


class HallPatch(BaseModel):
    """修改**现网**约束：立即生效，但只作用于之后新排的方案；历史不动。"""
    min_manhattan: int | None = None
    blocked_seats: list | None = None


def _serialize(r: Hall) -> dict:
    return {
        "id": r.id, "code": r.code, "name": r.name,
        "rows": r.rows, "cols": r.cols,
        "min_manhattan": r.min_manhattan,
        "blocked_seats": json.loads(r.blocked_seats or "[]"),
    }


@router.get("")
def list_halls(db: Session = Depends(get_db)):
    return [_serialize(r) for r in db.scalars(select(Hall).order_by(Hall.id)).all()]


@router.patch("/{hall_id}")
def update_hall(hall_id: int, body: HallPatch, db: Session = Depends(get_db)):
    hall = db.get(Hall, hall_id)
    if not hall:
        raise HTTPException(404, "考室不存在")
    if body.min_manhattan is not None:
        if body.min_manhattan < 1:
            raise HTTPException(422, "最小曼哈顿距离必须 >= 1")
        hall.min_manhattan = body.min_manhattan
    if body.blocked_seats is not None:
        # 归一化 + 丢弃越界坐标；只改现网约束，绝不触碰任何历史方案的座位。
        blocked = parse_blocked(body.blocked_seats, hall.rows, hall.cols)
        hall.blocked_seats = json.dumps([list(p) for p in sorted(blocked)])
    db.commit()
    db.refresh(hall)
    return _serialize(hall)
