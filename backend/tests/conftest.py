import os
import tempfile

# 必须在导入 app 之前指向独立 sqlite 库，避免碰开发库
_TMPDIR = tempfile.mkdtemp(prefix="hallspan_test_")
os.environ["DATABASE_URL"] = f"sqlite:///{_TMPDIR}/test.db"
os.environ["SEED_ON_EMPTY"] = "true"

import pytest
from fastapi.testclient import TestClient

from app.database import Base, SessionLocal, engine
from app.main import app
from app.services.seed import seed_if_empty


@pytest.fixture()
def client():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        seed_if_empty(db)
    finally:
        db.close()
    with TestClient(app) as c:
        yield c
