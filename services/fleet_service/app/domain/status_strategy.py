from drivenow_shared.enums import CarStatus

from app.domain.exceptions import InvalidStatusTransitionError

# Explicit allowed transitions (Strategy for status changes).
# Rental normally claims/releases via CAS (expected_status); maintenance is public.
ALLOWED_TRANSITIONS: dict[CarStatus, set[CarStatus]] = {
    CarStatus.AVAILABLE: {CarStatus.IN_USE, CarStatus.UNDER_MAINTENANCE},
    CarStatus.IN_USE: {CarStatus.AVAILABLE},
    CarStatus.UNDER_MAINTENANCE: {CarStatus.AVAILABLE},
}


class CarStatusStrategy:
    """Validates car status transitions according to fleet business rules."""

    def can_transition(self, current: CarStatus, new: CarStatus) -> bool:
        if current == new:
            return True
        return new in ALLOWED_TRANSITIONS.get(current, set())

    def validate(self, current: CarStatus, new: CarStatus) -> None:
        if not self.can_transition(current, new):
            raise InvalidStatusTransitionError(
                f"Cannot transition car status from '{current.value}' to '{new.value}'"
            )
