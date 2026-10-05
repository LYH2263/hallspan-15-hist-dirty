import json

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.models import Hall
from app.services.drift import parse_blocked

router = APIRouter(prefix="/halls", tags=["halls"])


def _hall_dict(r: Hall) -> dict:
    return {"id": r.id, "code": r.code, "name": r.name, "rows": r.rows, "cols": r.cols,
            "min_manhattan": r.min_manhattan, "blocked_seats": parse_blocked(r.blocked_seats)}


@router.get("")
def list_halls(db: Session = Depends(get_db)):
    return [_hall_dict(r) for r in db.scalars(select(Hall).order_by(Hall.id)).all()]


class HallUpdate(BaseModel):
    min_manhattan: int | None = Field(default=None, ge=1, le=10)
    blocked_seats: list[list[int]] | None = None


@router.patch("/{hall_id}")
def update_hall(hall_id: int, body: HallUpdate, db: Session = Depends(get_db)):
    """改现网约束（最小距/禁坐）。仅影响之后的新排座；历史方案只读，此处绝不触碰。"""
    hall = db.get(Hall, hall_id)
    if not hall:
        raise HTTPException(404, "考室不存在")
    if body.min_manhattan is not None:
        hall.min_manhattan = body.min_manhattan
    if body.blocked_seats is not None:
        norm = set()
        for p in body.blocked_seats:
            if not isinstance(p, (list, tuple)) or len(p) != 2:
                raise HTTPException(422, "禁坐格式应为 [[行,列],...]")
            r, c = int(p[0]), int(p[1])
            if not (0 <= r < hall.rows and 0 <= c < hall.cols):
                raise HTTPException(422, f"禁坐位置越界: ({r},{c})")
            norm.add((r, c))
        hall.blocked_seats = json.dumps([list(p) for p in sorted(norm)])
    db.commit()
    db.refresh(hall)
    return _hall_dict(hall)
