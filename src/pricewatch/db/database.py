from collections.abc import Generator
from pathlib import Path

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from pricewatch.config import get_settings


class Base(DeclarativeBase):
    pass


def _ensure_sqlite_dir(database_url: str) -> None:
    if database_url.startswith("sqlite:///"):
        db_path = Path(database_url.removeprefix("sqlite:///"))
        db_path.parent.mkdir(parents=True, exist_ok=True)


settings = get_settings()
_ensure_sqlite_dir(settings.database_url)

connect_args = {"check_same_thread": False} if settings.database_url.startswith("sqlite") else {}
engine = create_engine(settings.database_url, connect_args=connect_args)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


def _migrate_sqlite_columns() -> None:
    if not settings.database_url.startswith("sqlite"):
        return

    inspector = inspect(engine)
    if "tracked_items" in inspector.get_table_names():
        existing = {col["name"] for col in inspector.get_columns("tracked_items")}
        additions = {
            "preferred_site": "VARCHAR(255)",
            "also_search_other_sites": "BOOLEAN DEFAULT 1",
            "current_source_url": "VARCHAR(2048)",
            "current_source_site": "VARCHAR(255)",
        }
        with engine.begin() as conn:
            for name, ddl in additions.items():
                if name not in existing:
                    conn.execute(text(f"ALTER TABLE tracked_items ADD COLUMN {name} {ddl}"))

    if "price_history" in inspector.get_table_names():
        existing = {col["name"] for col in inspector.get_columns("price_history")}
        if "source_site" not in existing:
            with engine.begin() as conn:
                conn.execute(text("ALTER TABLE price_history ADD COLUMN source_site VARCHAR(255)"))


def init_db() -> None:
    from pricewatch.db import models  # noqa: F401

    Base.metadata.create_all(bind=engine)
    _migrate_sqlite_columns()


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
