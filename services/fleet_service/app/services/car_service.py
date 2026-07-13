import logging
from dataclasses import dataclass

from drivenow_shared.enums import CarStatus, DomainEventType
from drivenow_shared.events import DomainEvent

from app.core.metrics import set_active_cars, set_available_cars
from app.domain.events import EventPublisher
from app.domain.exceptions import ConflictError, NotFoundError
from app.domain.status_strategy import CarStatusStrategy
from app.repositories.car_repository import CarRepository
from app.repositories.models import CarModel
from app.schemas.car import CarCreate, CarDetailsUpdate, CarStatusUpdate

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class StatusUpdateResult:
    car: CarModel
    changed: bool


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
        set_active_cars(self._repository.count_by_status(CarStatus.IN_USE))

    def add_car(self, payload: CarCreate) -> CarModel:
        car = CarModel(
            model=payload.model,
            year=payload.year,
            status=CarStatus.AVAILABLE,
        )
        created = self._repository.add(car)
        logger.info(
            "Car %s was added successfully (model=%s year=%s).",
            created.id,
            created.model,
            created.year,
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

    def delete_car(self, car_id: int) -> None:
        car = self._repository.get_by_id_for_update(car_id)
        if car is None:
            raise NotFoundError(f"Car {car_id} not found")
        if car.status == CarStatus.IN_USE:
            raise ConflictError(
                f"Car {car_id} is in use and cannot be deleted — end the rental first"
            )

        self._repository.delete(car)
        logger.info(
            "Car %s was deleted successfully (model=%s year=%s).",
            car_id,
            car.model,
            car.year,
        )
        self._events.publish(
            DomainEvent(
                event_type=DomainEventType.CAR_DELETED,
                entity_type="car",
                entity_id=str(car_id),
                payload={
                    "model": car.model,
                    "year": car.year,
                    "status": car.status.value,
                },
            )
        )
        self._refresh_metrics()

    def update_car_details(self, car_id: int, payload: CarDetailsUpdate) -> CarModel:
        if payload.model is None and payload.year is None:
            raise ConflictError("Provide at least one of model or year to update")

        car = self._repository.get_by_id_for_update(car_id)
        if car is None:
            raise NotFoundError(f"Car {car_id} not found")

        previous_status = car.status
        if payload.model is not None:
            car.model = payload.model
        if payload.year is not None:
            car.year = payload.year

        updated = self._repository.save(car)
        self._publish_update_events(previous_status, updated)
        self._refresh_metrics()
        return updated

    def update_car_status(self, car_id: int, payload: CarStatusUpdate) -> StatusUpdateResult:
        if payload.expected_status is not None:
            return self._compare_and_set_status(
                car_id,
                expected_status=payload.expected_status,
                new_status=payload.status,
            )

        car = self._repository.get_by_id_for_update(car_id)
        if car is None:
            raise NotFoundError(f"Car {car_id} not found")

        if car.status == payload.status:
            logger.info(
                "Car %s status is already '%s' — no change applied.",
                car.id,
                car.status.value,
            )
            return StatusUpdateResult(car=car, changed=False)

        previous_status = car.status
        self._status_strategy.validate(car.status, payload.status)
        car.status = payload.status

        updated = self._repository.save(car)
        self._publish_update_events(previous_status, updated)
        self._refresh_metrics()
        return StatusUpdateResult(car=updated, changed=True)

    def _compare_and_set_status(
        self,
        car_id: int,
        expected_status: CarStatus,
        new_status: CarStatus,
    ) -> StatusUpdateResult:
        self._status_strategy.validate(expected_status, new_status)

        if expected_status == new_status:
            existing = self._repository.get_by_id(car_id)
            if existing is None:
                raise NotFoundError(f"Car {car_id} not found")
            if existing.status == new_status:
                logger.info(
                    "Car %s status is already '%s' — no change applied.",
                    existing.id,
                    existing.status.value,
                )
                return StatusUpdateResult(car=existing, changed=False)

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
        return StatusUpdateResult(car=updated, changed=True)

    def _publish_update_events(
        self, previous_status: CarStatus, updated: CarModel
    ) -> None:
        logger.info(
            "Car %s was updated successfully (model=%s year=%s status=%s).",
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
