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
    """Seed Prometheus gauges from the DB before the first mutation."""
    # Same refresh path as write handlers.
    settings = get_settings()
    db = SessionLocal()
    try:
        RentalService(
            SqlAlchemyRentalRepository(db),
            HttpFleetClient(
                settings.fleet_service_url,
                internal_token=settings.internal_service_token,
            ),
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
    """Build and wire the rental FastAPI application."""
    settings = get_settings()
    application = FastAPI(title="DriveNow Rental Service", lifespan=lifespan)
    install_metrics_middleware(application, settings.app_name)
    application.include_router(rentals.router)
    application.include_router(health.router)
    return application


app = create_app()
