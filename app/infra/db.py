from __future__ import annotations

from urllib.parse import quote_plus

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker
from app.settings import settings


class Base(DeclarativeBase):
    pass


def database_url() -> str:
    user = settings.DB_USER
    pwd = quote_plus(settings.DB_PASS)  # evita romper URL si hay caracteres especiales
    host = settings.DB_HOST
    port = settings.DB_PORT
    name = settings.DB_NAME

    return f"mysql+pymysql://{user}:{pwd}@{host}:{port}/{name}?charset=utf8mb4"


engine = create_engine(
    database_url(),
    pool_pre_ping=True,
    pool_recycle=1800,   # evita conexiones muertas (común en MySQL)
    pool_size=10,
    max_overflow=20,
    future=True,
)

SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False, future=True)


def get_db():
    """Dependency para FastAPI."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def get_db_session():
    """Helper opcional para scripts/CLI."""
    return SessionLocal()