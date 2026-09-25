import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from pricewatch.db.database import Base


@pytest.fixture
def db_session() -> Session:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine, autoflush=False, autocommit=False)()
    try:
        yield session
    finally:
        session.close()
