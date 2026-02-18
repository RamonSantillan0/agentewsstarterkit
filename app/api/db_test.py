from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.orm import Session
from app.infra.db import get_db

router = APIRouter()

@router.get("/db-test")
def db_test(db: Session = Depends(get_db)):
    v = db.execute(text("SELECT 1")).scalar()
    return {"ok": True, "value": v}