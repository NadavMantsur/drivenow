from collections.abc import Generator

from fastapi import Depends
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.domain.events import EventPublisher, NoOpEventPublisher
from app.domain.status_strategy import CarStatusStrategy
from app.repositories.car_repository import CarRepository, SqlAlchemyCarRepository
from app.services.car_service import CarService


def get_car_repository(db: Session = Depends(get_db)) -> Generator[CarRepository, None, None]:
    yield SqlAlchemyCarRepository(db)


def get_status_strategy() -> CarStatusStrategy:
    return CarStatusStrategy()


def get_event_publisher() -> EventPublisher:
    return NoOpEventPublisher()


def get_car_service(
    repository: CarRepository = Depends(get_car_repository),
    status_strategy: CarStatusStrategy = Depends(get_status_strategy),
    event_publisher: EventPublisher = Depends(get_event_publisher),
) -> CarService:
    return CarService(repository, status_strategy, event_publisher)
