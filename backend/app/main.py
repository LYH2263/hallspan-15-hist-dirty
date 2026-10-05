from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text

from app.api.router import api_router
from app.config import settings
from app.database import Base, SessionLocal, engine
from app.services.seed import seed_if_empty


def _ensure_columns() -> None:
    """轻量幂等补列（老库从快照版本升级；create_all 不会给既有表加列）。

    blocked_seats 是**现网**约束，补列绝不改动任何已冻结的历史方案。
    """
    with engine.begin() as conn:
        if engine.dialect.name == "postgresql":
            conn.execute(text(
                "ALTER TABLE halls ADD COLUMN IF NOT EXISTS blocked_seats TEXT DEFAULT '[]'"
            ))


@asynccontextmanager
async def lifespan(_app: FastAPI):
    Base.metadata.create_all(bind=engine)
    _ensure_columns()
    if settings.seed_on_empty:
        db = SessionLocal()
        try:
            seed_if_empty(db)
        finally:
            db.close()
    yield


app = FastAPI(title="HallSpan", version="0.1.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(api_router, prefix="/api")
