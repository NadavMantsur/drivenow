from unittest.mock import MagicMock

import pytest

from drivenow_shared.enums import CarStatus

from app.domain.events import NoOpEventPublisher
from app.domain.exceptions import (
    ConflictError,
    ForbiddenError,
    InvalidStatusTransitionError,
    NotFoundError,
)
from app.domain.status_strategy import CarStatusStrategy
from app.repositories.models import CarModel
from app.schemas.car import CarCreate, CarDetailsUpdate, CarStatusUpdate
from app.services.car_service import CarService

INTERNAL_TOKEN = "test-internal-token"


def _service(repo: MagicMock) -> CarService:
    return CarService(
        repo,
        CarStatusStrategy(),
        NoOpEventPublisher(),
        internal_service_token=INTERNAL_TOKEN,
    )


def test_add_car_defaults_to_available():
    repo = MagicMock()
    created = CarModel(id=1, model="Corolla", year=2024, status=CarStatus.AVAILABLE)
    repo.add.return_value = created
    repo.count_by_status.return_value = 1

    service = _service(repo)
    result = service.add_car(CarCreate(model="Corolla", year=2024))

    assert result.status == CarStatus.AVAILABLE
    assert repo.add.called


def test_delete_car_removes_available_car():
    repo = MagicMock()
    car = CarModel(id=1, model="Corolla", year=2024, status=CarStatus.AVAILABLE)
    repo.get_by_id_for_update.return_value = car
    repo.count_by_status.return_value = 0

    service = _service(repo)
    service.delete_car(1)

    repo.delete.assert_called_once_with(car)


def test_delete_car_rejects_in_use():
    repo = MagicMock()
    repo.get_by_id_for_update.return_value = CarModel(
        id=1, model="Corolla", year=2024, status=CarStatus.IN_USE
    )
    service = _service(repo)

    with pytest.raises(ConflictError, match="in use"):
        service.delete_car(1)
    repo.delete.assert_not_called()


def test_delete_car_not_found():
    repo = MagicMock()
    repo.get_by_id_for_update.return_value = None
    service = _service(repo)

    with pytest.raises(NotFoundError, match="not found"):
        service.delete_car(99)


def test_update_car_status_rejects_illegal_transition():
    repo = MagicMock()
    repo.get_by_id_for_update.return_value = CarModel(
        id=1,
        model="Corolla",
        year=2024,
        status=CarStatus.UNDER_MAINTENANCE,
    )
    service = _service(repo)

    with pytest.raises(InvalidStatusTransitionError, match="Cannot transition"):
        service.update_car_status(
            1,
            CarStatusUpdate(status=CarStatus.IN_USE),
            caller_token=INTERNAL_TOKEN,
        )


def test_update_car_status_noop_when_already_same():
    repo = MagicMock()
    car = CarModel(
        id=1, model="Corolla", year=2024, status=CarStatus.UNDER_MAINTENANCE
    )
    repo.get_by_id_for_update.return_value = car
    service = _service(repo)

    result = service.update_car_status(
        1, CarStatusUpdate(status=CarStatus.UNDER_MAINTENANCE)
    )

    assert result.changed is False
    assert result.car.status == CarStatus.UNDER_MAINTENANCE
    repo.save.assert_not_called()


def test_update_car_status_noop_when_already_available():
    repo = MagicMock()
    car = CarModel(id=2, model="Civic", year=2022, status=CarStatus.AVAILABLE)
    repo.get_by_id_for_update.return_value = car
    service = _service(repo)

    result = service.update_car_status(2, CarStatusUpdate(status=CarStatus.AVAILABLE))

    assert result.changed is False
    assert result.car.status == CarStatus.AVAILABLE
    repo.save.assert_not_called()


def test_compare_and_set_status_success():
    repo = MagicMock()
    updated = CarModel(id=1, model="Corolla", year=2024, status=CarStatus.IN_USE)
    repo.transition_status.return_value = updated
    repo.count_by_status.return_value = 0

    service = _service(repo)
    result = service.update_car_status(
        1,
        CarStatusUpdate(status=CarStatus.IN_USE, expected_status=CarStatus.AVAILABLE),
        caller_token=INTERNAL_TOKEN,
    )

    assert result.changed is True
    assert result.car.status == CarStatus.IN_USE
    repo.transition_status.assert_called_once_with(
        1, CarStatus.AVAILABLE, CarStatus.IN_USE
    )


def test_compare_and_set_status_conflict():
    repo = MagicMock()
    repo.transition_status.return_value = None
    repo.get_by_id.return_value = CarModel(
        id=1, model="Corolla", year=2024, status=CarStatus.IN_USE
    )

    service = _service(repo)

    with pytest.raises(ConflictError, match="expected 'available'"):
        service.update_car_status(
            1,
            CarStatusUpdate(status=CarStatus.IN_USE, expected_status=CarStatus.AVAILABLE),
            caller_token=INTERNAL_TOKEN,
        )


def test_public_cannot_claim_or_release_in_use_via_cas():
    """Public CAS without token must not bypass rental ownership of in_use."""
    repo = MagicMock()
    service = _service(repo)

    with pytest.raises(ForbiddenError, match="in_use"):
        service.update_car_status(
            1,
            CarStatusUpdate(status=CarStatus.IN_USE, expected_status=CarStatus.AVAILABLE),
        )
    with pytest.raises(ForbiddenError, match="in_use"):
        service.update_car_status(
            1,
            CarStatusUpdate(
                status=CarStatus.AVAILABLE, expected_status=CarStatus.IN_USE
            ),
        )
    repo.transition_status.assert_not_called()


def test_public_cannot_claim_in_use_without_cas():
    repo = MagicMock()
    repo.get_by_id_for_update.return_value = CarModel(
        id=1, model="Corolla", year=2024, status=CarStatus.AVAILABLE
    )
    service = _service(repo)

    with pytest.raises(ForbiddenError, match="in_use"):
        service.update_car_status(1, CarStatusUpdate(status=CarStatus.IN_USE))
    repo.save.assert_not_called()


def test_update_car_status_rejects_direct_change_while_in_use_without_token():
    repo = MagicMock()
    repo.get_by_id_for_update.return_value = CarModel(
        id=1, model="Corolla", year=2024, status=CarStatus.IN_USE
    )
    service = _service(repo)

    with pytest.raises(ForbiddenError, match="in_use"):
        service.update_car_status(1, CarStatusUpdate(status=CarStatus.AVAILABLE))
    with pytest.raises(ForbiddenError, match="in_use"):
        service.update_car_status(
            1, CarStatusUpdate(status=CarStatus.UNDER_MAINTENANCE)
        )
    repo.save.assert_not_called()


def test_wrong_internal_token_is_rejected():
    repo = MagicMock()
    service = _service(repo)

    with pytest.raises(ForbiddenError, match="in_use"):
        service.update_car_status(
            1,
            CarStatusUpdate(status=CarStatus.IN_USE, expected_status=CarStatus.AVAILABLE),
            caller_token="wrong-token",
        )


def test_compare_and_set_releases_in_use_to_available():
    """Rental end path: CAS in_use → available with internal token."""
    repo = MagicMock()
    updated = CarModel(id=1, model="Corolla", year=2024, status=CarStatus.AVAILABLE)
    repo.transition_status.return_value = updated
    repo.count_by_status.return_value = 1

    service = _service(repo)
    result = service.update_car_status(
        1,
        CarStatusUpdate(
            status=CarStatus.AVAILABLE, expected_status=CarStatus.IN_USE
        ),
        caller_token=INTERNAL_TOKEN,
    )

    assert result.changed is True
    assert result.car.status == CarStatus.AVAILABLE
    repo.transition_status.assert_called_once_with(
        1, CarStatus.IN_USE, CarStatus.AVAILABLE
    )


def test_compare_and_set_rejects_in_use_to_maintenance():
    repo = MagicMock()
    service = _service(repo)

    with pytest.raises(InvalidStatusTransitionError, match="Cannot transition"):
        service.update_car_status(
            1,
            CarStatusUpdate(
                status=CarStatus.UNDER_MAINTENANCE,
                expected_status=CarStatus.IN_USE,
            ),
            caller_token=INTERNAL_TOKEN,
        )
    repo.transition_status.assert_not_called()


def test_maintenance_transitions_remain_public():
    repo = MagicMock()
    car = CarModel(id=1, model="Corolla", year=2024, status=CarStatus.AVAILABLE)
    repo.get_by_id_for_update.return_value = car
    repo.save.side_effect = lambda c: c
    repo.count_by_status.return_value = 0

    service = _service(repo)
    result = service.update_car_status(
        1, CarStatusUpdate(status=CarStatus.UNDER_MAINTENANCE)
    )

    assert result.changed is True
    assert result.car.status == CarStatus.UNDER_MAINTENANCE


def test_update_car_details():
    repo = MagicMock()
    car = CarModel(id=1, model="Corolla", year=2024, status=CarStatus.AVAILABLE)
    repo.get_by_id_for_update.return_value = car
    repo.save.side_effect = lambda c: c
    repo.count_by_status.return_value = 1

    service = _service(repo)
    result = service.update_car_details(
        1, CarDetailsUpdate(model="Corolla Hybrid", year=2025)
    )

    assert result.model == "Corolla Hybrid"
    assert result.year == 2025
    assert result.status == CarStatus.AVAILABLE
