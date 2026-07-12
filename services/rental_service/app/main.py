from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api.routers import health, rentals
from app.core.config import get_settings
from app.core.database import init_db
from app.core.logging import setup_logging
from app.core.metrics import install_metrics_middleware


@asynccontextmanager
async def lifespan(_: FastAPI):
    settings = get_settings()
    setup_logging(settings.app_name, settings.log_dir, settings.log_level)
    init_db()
    yield


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(title="DriveNow Rental Service", lifespan=lifespan)
    install_metrics_middleware(app, settings.app_name)
    app.include_router(rentals.router)
    app.include_router(health.router)
    return app


app = create_app()
