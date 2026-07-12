import logging

from drivenow_shared.enums import CarStatus, DomainEventType
from drivenow_shared.events import DomainEvent

from app.core.metrics import set_available_cars
from app.domain.events import EventPublisher
from app.domain.exceptions import ConflictError, NotFoundError
from app.domain.status_strategy import CarStatusStrategy
from app.repositories.car_repository import CarRepository
from app.repositories.models import CarModel
from app.schemas.car import CarCreate, CarUpdate

logger = logging.getLogger(__name__)


class CarService:
    def __init__(
        self,
        repository: CarRepository,
        status_strategy: CarStatusStrategy,
        event_publisher: EventPublisher,
    ) -> None:
        self._repository = repository
        self._status_strategy = status_strategy
        self._events = event_publisher

    def _refresh_metrics(self) -> None:
        set_available_cars(self._repository.count_by_status(CarStatus.AVAILABLE))

    def add_car(self, payload: CarCreate) -> CarModel:
        car = CarModel(
            model=payload.model,
            year=payload.year,
            status=CarStatus.AVAILABLE,
        )
        created = self._repository.add(car)
        logger.info(
            "Car added id=%s model=%s year=%s status=%s",
            created.id,
            created.model,
            created.year,
            created.status.value,
        )
        self._events.publish(
            DomainEvent(
                event_type=DomainEventType.CAR_CREATED,
                entity_type="car",
                entity_id=str(created.id),
                payload={
                    "model": created.model,
                    "year": created.year,
                    "status": created.status.value,
                },
            )
        )
        self._refresh_metrics()
        return created

    def list_cars(self, status: CarStatus | None = None) -> list[CarModel]:
        return self._repository.list(status=status)

    def get_car(self, car_id: int) -> CarModel:
        car = self._repository.get_by_id(car_id)
        if car is None:
            raise NotFoundError(f"Car {car_id} not found")
        return car

    def update_car(self, car_id: int, payload: CarUpdate) -> CarModel:
        if payload.status is not None and payload.expected_status is not None:
            return self._compare_and_set_status(
                car_id,
                expected_status=payload.expected_status,
                new_status=payload.status,
                model=payload.model,
                year=payload.year,
            )

        # Lock the row so concurrent status updates serialize on the same car.
        car = self._repository.get_by_id_for_update(car_id)
        if car is None:
            raise NotFoundError(f"Car {car_id} not found")

        previous_status = car.status

        if payload.model is not None:
            car.model = payload.model
        if payload.year is not None:
            car.year = payload.year
        if payload.status is not None:
            self._status_strategy.validate(car.status, payload.status)
            car.status = payload.status

        updated = self._repository.save(car)
        self._publish_update_events(previous_status, updated)
        self._refresh_metrics()
        return updated

    def _compare_and_set_status(
        self,
        car_id: int,
        expected_status: CarStatus,
        new_status: CarStatus,
        model: str | None = None,
        year: int | None = None,
    ) -> CarModel:
        self._status_strategy.validate(expected_status, new_status)

        if model is not None or year is not None:
            # CAS is status-only; reject mixed updates to keep the atomic path simple.
            raise ConflictError(
                "expected_status cannot be combined with model/year updates"
            )

        updated = self._repository.transition_status(
            car_id, expected_status, new_status
        )
        if updated is None:
            existing = self._repository.get_by_id(car_id)
            if existing is None:
                raise NotFoundError(f"Car {car_id} not found")
            raise ConflictError(
                f"Car {car_id} status is '{existing.status.value}', "
                f"expected '{expected_status.value}' for transition to '{new_status.value}'"
            )

        logger.info(
            "Car status CAS id=%s from=%s to=%s",
            updated.id,
            expected_status.value,
            new_status.value,
        )
        self._publish_update_events(expected_status, updated)
        self._refresh_metrics()
        return updated

    def _publish_update_events(
        self, previous_status: CarStatus, updated: CarModel
    ) -> None:
        logger.info(
            "Car updated id=%s model=%s year=%s status=%s",
            updated.id,
            updated.model,
            updated.year,
            updated.status.value,
        )
        if previous_status != updated.status:
            self._events.publish(
                DomainEvent(
                    event_type=DomainEventType.CAR_STATUS_CHANGED,
                    entity_type="car",
                    entity_id=str(updated.id),
                    payload={
                        "from": previous_status.value,
                        "to": updated.status.value,
                    },
                )
            )
        else:
            self._events.publish(
                DomainEvent(
                    event_type=DomainEventType.CAR_UPDATED,
                    entity_type="car",
                    entity_id=str(updated.id),
                    payload={
                        "model": updated.model,
                        "year": updated.year,
                        "status": updated.status.value,
                    },
                )
            )
