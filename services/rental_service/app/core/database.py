from collections.abc import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.core.config import get_settings


class Base(DeclarativeBase):
    pass


settings = get_settings()
engine = create_engine(settings.database_url, pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db() -> None:
    from sqlalchemy import text

    from app.repositories import models  # noqa: F401

    Base.metadata.create_all(bind=engine)
    # create_all does not add new indexes to existing tables — ensure concurrency guard.
    with engine.begin() as conn:
        conn.execute(
            text(
                "CREATE UNIQUE INDEX IF NOT EXISTS uq_rentals_one_ongoing_per_car "
                "ON rentals (car_id) WHERE end_date IS NULL"
            )
        )
