from drivenow_shared.enums import CarStatus

from app.domain.exceptions import InvalidStatusTransitionError
from app.domain.status_strategy import CarStatusStrategy


def test_allows_available_to_in_use():
    strategy = CarStatusStrategy()
    strategy.validate(CarStatus.AVAILABLE, CarStatus.IN_USE)


def test_rejects_maintenance_to_in_use():
    strategy = CarStatusStrategy()
    try:
        strategy.validate(CarStatus.UNDER_MAINTENANCE, CarStatus.IN_USE)
        assert False, "expected InvalidStatusTransitionError"
    except InvalidStatusTransitionError:
        pass
