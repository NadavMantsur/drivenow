from collections.abc import Generator

from fastapi import Depends
from sqlalchemy.orm import Session

from app.clients.fleet_client import FleetClient, HttpFleetClient
from app.core.config import get_settings
from app.core.database import get_db
from app.domain.events import EventPublisher, NoOpEventPublisher
from app.repositories.rental_repository import RentalRepository, SqlAlchemyRentalRepository
from app.services.rental_service import RentalService


def get_rental_repository(
    db: Session = Depends(get_db),
) -> Generator[RentalRepository, None, None]:
    yield SqlAlchemyRentalRepository(db)


def get_fleet_client() -> FleetClient:
    settings = get_settings()
    return HttpFleetClient(
        settings.fleet_service_url,
        internal_token=settings.internal_service_token,
    )


def get_event_publisher() -> EventPublisher:
    return NoOpEventPublisher()


def get_rental_service(
    repository: RentalRepository = Depends(get_rental_repository),
    fleet_client: FleetClient = Depends(get_fleet_client),
    event_publisher: EventPublisher = Depends(get_event_publisher),
) -> RentalService:
    return RentalService(repository, fleet_client, event_publisher)
