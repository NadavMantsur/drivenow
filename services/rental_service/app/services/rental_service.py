import logging
from datetime import datetime, timezone

from drivenow_shared.enums import CarStatus, DomainEventType
from drivenow_shared.events import DomainEvent
from sqlalchemy.exc import IntegrityError

from app.clients.fleet_client import FleetClient
from app.core.metrics import set_ongoing_rentals
from app.domain.events import EventPublisher
from app.domain.exceptions import ConflictError, NotFoundError
from app.repositories.models import RentalModel
from app.repositories.rental_repository import RentalRepository
from app.schemas.rental import RentalCreate

logger = logging.getLogger(__name__)


class RentalService:
    def __init__(
        self,
        repository: RentalRepository,
        fleet_client: FleetClient,
        event_publisher: EventPublisher,
    ) -> None:
        self._repository = repository
        self._fleet = fleet_client
        self._events = event_publisher

    def refresh_metrics(self) -> None:
        set_ongoing_rentals(self._repository.count_ongoing())

    def list_rentals(self, *, ongoing: bool | None = None) -> list[RentalModel]:
        return self._repository.list(ongoing=ongoing)

    def _compensate_car_status(
        self,
        car_id: int,
        status: CarStatus,
        *,
        expected_status: CarStatus,
        reason: str,
    ) -> None:
        try:
            self._fleet.update_car_status(
                car_id, status, expected_status=expected_status
            )
            logger.warning(
                "Compensated car_id=%s to %s (%s)", car_id, status.value, reason
            )
        except Exception:
            logger.exception(
                "Compensation failed for car_id=%s after %s — manual reconcile may be needed",
                car_id,
                reason,
            )

    def register_rental(self, payload: RentalCreate) -> RentalModel:
        if self._repository.has_ongoing_for_car(payload.car_id):
            raise ConflictError(f"Car {payload.car_id} already has an ongoing rental")

        car = self._fleet.get_car(payload.car_id)
        car_status = CarStatus(car["status"])
        if car_status != CarStatus.AVAILABLE:
            raise ConflictError(
                f"Car {payload.car_id} is not available (status={car_status.value})"
            )

        # Atomic claim: only one concurrent register can win available → in_use.
        self._fleet.update_car_status(
            payload.car_id,
            CarStatus.IN_USE,
            expected_status=CarStatus.AVAILABLE,
        )

        rental = RentalModel(
            car_id=payload.car_id,
            customer_name=payload.customer_name,
            start_date=datetime.now(timezone.utc),
            end_date=None,
        )
        try:
            created = self._repository.add(rental)
        except IntegrityError as exc:
            # Another ongoing rental exists — leave car in_use for that owner.
            logger.warning(
                "Concurrent register lost for car_id=%s: %s",
                payload.car_id,
                exc,
            )
            raise ConflictError(
                f"Car {payload.car_id} already has an ongoing rental"
            ) from exc
        except Exception:
            self._compensate_car_status(
                payload.car_id,
                CarStatus.AVAILABLE,
                expected_status=CarStatus.IN_USE,
                reason="rental insert failed after fleet marked in_use",
            )
            raise

        logger.info(
            "Rental %s was registered successfully for car %s (customer=%s).",
            created.id,
            created.car_id,
            created.customer_name,
        )
        self._events.publish(
            DomainEvent(
                event_type=DomainEventType.RENTAL_CREATED,
                entity_type="rental",
                entity_id=str(created.id),
                payload={
                    "car_id": created.car_id,
                    "customer_name": created.customer_name,
                    "start_date": created.start_date.isoformat(),
                },
            )
        )
        self.refresh_metrics()
        return created

    def end_rental(self, rental_id: int) -> RentalModel:
        rental = self._repository.get_by_id(rental_id)
        if rental is None:
            raise NotFoundError(f"Rental {rental_id} not found")
        if rental.end_date is not None:
            raise ConflictError(f"Rental {rental_id} is already ended")

        # Release fleet first (CAS), then commit end_date — avoids "ended but still in_use".
        # If the car was already deleted from fleet, still close the orphan rental.
        try:
            self._fleet.update_car_status(
                rental.car_id,
                CarStatus.AVAILABLE,
                expected_status=CarStatus.IN_USE,
            )
        except NotFoundError:
            logger.warning(
                "Car %s not found in fleet while ending rental %s — closing rental anyway",
                rental.car_id,
                rental_id,
            )

        rental.end_date = datetime.now(timezone.utc)
        try:
            updated = self._repository.save(rental)
        except Exception:
            self._compensate_car_status(
                rental.car_id,
                CarStatus.IN_USE,
                expected_status=CarStatus.AVAILABLE,
                reason="rental end persist failed after fleet restored available",
            )
            raise

        logger.info(
            "Rental %s was ended successfully; car %s is available again.",
            updated.id,
            updated.car_id,
        )
        self._events.publish(
            DomainEvent(
                event_type=DomainEventType.RENTAL_ENDED,
                entity_type="rental",
                entity_id=str(updated.id),
                payload={
                    "car_id": updated.car_id,
                    "end_date": updated.end_date.isoformat(),
                },
            )
        )
        self.refresh_metrics()
        return updated
