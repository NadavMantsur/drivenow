from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api.routers import cars, health
from app.core.config import get_settings
from app.core.database import SessionLocal, init_db
from app.core.logging import setup_logging
from app.core.metrics import install_metrics_middleware
from app.domain.events import NoOpEventPublisher
from app.domain.status_strategy import CarStatusStrategy
from app.repositories.car_repository import SqlAlchemyCarRepository
from app.services.car_service import CarService


def seed_metrics() -> None:
    # Seed Prometheus gauges from the DB so /metrics is correct before the first
    # mutation (same refresh path as write handlers).
    db = SessionLocal()
    try:
        CarService(
            SqlAlchemyCarRepository(db),
            CarStatusStrategy(),
            NoOpEventPublisher(),
        ).refresh_metrics()
    finally:
        db.close()


@asynccontextmanager
async def lifespan(_: FastAPI):
    settings = get_settings()
    setup_logging(settings.app_name, settings.log_dir, settings.log_level)
    init_db()
    seed_metrics()
    yield


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(title="DriveNow Fleet Service", lifespan=lifespan)
    install_metrics_middleware(app, settings.app_name)
    app.include_router(cars.router)
    app.include_router(health.router)
    return app


app = create_app()
