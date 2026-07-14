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

_COMPENSATION_ATTEMPTS = 3


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
        attempts: int = _COMPENSATION_ATTEMPTS,
    ) -> bool:
        """Best-effort CAS reverse. Returns True if compensation applied."""
        last_error: Exception | None = None
        for attempt in range(1, attempts + 1):
            try:
                self._fleet.update_car_status(
                    car_id, status, expected_status=expected_status
                )
                logger.warning(
                    "Compensated car_id=%s to %s (%s, attempt %s/%s)",
                    car_id,
                    status.value,
                    reason,
                    attempt,
                    attempts,
                )
                return True
            except Exception as exc:
                last_error = exc
                logger.warning(
                    "Compensation attempt %s/%s failed for car_id=%s after %s: %s",
                    attempt,
                    attempts,
                    car_id,
                    reason,
                    exc,
                )
        logger.error(
            "Compensation exhausted for car_id=%s after %s — heal paths may recover; last error=%s",
            car_id,
            reason,
            last_error,
        )
        return False

    def _heal_orphan_in_use(self, car_id: int, status: CarStatus) -> CarStatus:
        """Release in_use with no ongoing rental (timeout / failed compensation leftover)."""
        if status != CarStatus.IN_USE:
            return status
        if self._repository.has_ongoing_for_car(car_id):
            return status

        logger.warning(
            "Healing orphan in_use on car_id=%s (no ongoing rental) before register",
            car_id,
        )
        try:
            self._fleet.update_car_status(
                car_id,
                CarStatus.AVAILABLE,
                expected_status=CarStatus.IN_USE,
            )
            return CarStatus.AVAILABLE
        except ConflictError:
            car = self._fleet.get_car(car_id)
            return CarStatus(car["status"])

    def _release_car_for_end(self, car_id: int, rental_id: int) -> None:
        """CAS in_use→available, or heal when fleet is already released / car deleted."""
        try:
            self._fleet.update_car_status(
                car_id,
                CarStatus.AVAILABLE,
                expected_status=CarStatus.IN_USE,
            )
            return
        except NotFoundError:
            logger.warning(
                "Car %s not found in fleet while ending rental %s — closing rental anyway",
                car_id,
                rental_id,
            )
            return
        except ConflictError:
            pass

        try:
            car = self._fleet.get_car(car_id)
        except NotFoundError:
            logger.warning(
                "Car %s not found in fleet while ending rental %s — closing rental anyway",
                car_id,
                rental_id,
            )
            return

        status = CarStatus(car["status"])
        if status in (CarStatus.AVAILABLE, CarStatus.UNDER_MAINTENANCE):
            logger.warning(
                "Car %s is '%s' while ending rental %s — closing rental to heal desync",
                car_id,
                status.value,
                rental_id,
            )
            return

        raise ConflictError(
            f"Cannot end rental {rental_id}: car {car_id} status is '{status.value}'"
        )

    def register_rental(self, payload: RentalCreate) -> RentalModel:
        if self._repository.has_ongoing_for_car(payload.car_id):
            raise ConflictError(f"Car {payload.car_id} already has an ongoing rental")

        car = self._fleet.get_car(payload.car_id)
        car_status = self._heal_orphan_in_use(
            payload.car_id, CarStatus(car["status"])
        )
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
            # Another writer inserted an ongoing rental. Re-check: only leave
            # in_use if that rental exists; otherwise reverse our claim.
            if self._repository.has_ongoing_for_car(payload.car_id):
                logger.warning(
                    "Concurrent register lost for car_id=%s: %s",
                    payload.car_id,
                    exc,
                )
            else:
                self._compensate_car_status(
                    payload.car_id,
                    CarStatus.AVAILABLE,
                    expected_status=CarStatus.IN_USE,
                    reason="integrity error after CAS but no ongoing rental",
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
        # Heal when fleet is already available (failed compensation / ambiguous timeout).
        self._release_car_for_end(rental.car_id, rental_id)

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
