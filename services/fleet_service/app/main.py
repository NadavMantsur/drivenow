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
    """Seed Prometheus gauges from the DB before the first mutation."""
    # Same refresh path as write handlers.
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
    """App startup: logging, DB schema, metric gauges."""
    settings = get_settings()
    setup_logging(settings.app_name, settings.log_dir, settings.log_level)
    init_db()
    seed_metrics()
    yield


def create_app() -> FastAPI:
    """Build and wire the fleet FastAPI application."""
    settings = get_settings()
    application = FastAPI(title="DriveNow Fleet Service", lifespan=lifespan)
    install_metrics_middleware(application, settings.app_name)
    application.include_router(cars.router)
    application.include_router(health.router)
    return application


app = create_app()
