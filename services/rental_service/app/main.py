from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api.routers import health, rentals
from app.clients.fleet_client import HttpFleetClient
from app.core.config import get_settings
from app.core.database import SessionLocal, init_db
from app.core.logging import setup_logging
from app.core.metrics import install_metrics_middleware
from app.domain.events import NoOpEventPublisher
from app.repositories.rental_repository import SqlAlchemyRentalRepository
from app.services.rental_service import RentalService


def seed_metrics() -> None:
    # Seed Prometheus gauges from the DB so /metrics is correct before the first
    # mutation (same refresh path as write handlers).
    settings = get_settings()
    db = SessionLocal()
    try:
        RentalService(
            SqlAlchemyRentalRepository(db),
            HttpFleetClient(settings.fleet_service_url),
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
    app = FastAPI(title="DriveNow Rental Service", lifespan=lifespan)
    install_metrics_middleware(app, settings.app_name)
    app.include_router(rentals.router)
    app.include_router(health.router)
    return app


app = create_app()
