from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.db import get_db

router = APIRouter()


@router.get("/healthz")
def healthz(db: Session = Depends(get_db)) -> dict:
    """Liveness + DB check (SPEC §10)."""
    db.execute(text("SELECT 1"))
    return {"status": "ok", "db": "ok"}
