from datetime import datetime, timezone
from unittest.mock import MagicMock, call

import pytest
from sqlalchemy.exc import IntegrityError

from drivenow_shared.enums import CarStatus

from app.domain.events import NoOpEventPublisher
from app.domain.exceptions import ConflictError, FleetServiceError, NotFoundError
from app.repositories.models import RentalModel
from app.schemas.rental import RentalCreate
from app.services.rental_service import RentalService


def _rental(
    rental_id: int,
    *,
    car_id: int = 1,
    customer: str = "Alice",
    ended: bool = False,
) -> RentalModel:
    return RentalModel(
        id=rental_id,
        car_id=car_id,
        customer_name=customer,
        start_date=datetime.now(timezone.utc),
        end_date=datetime.now(timezone.utc) if ended else None,
    )


def test_register_rental_fails_when_car_not_available():
    repo = MagicMock()
    repo.has_ongoing_for_car.return_value = False
    fleet = MagicMock()
    fleet.get_car.return_value = {
        "id": 1,
        "status": CarStatus.UNDER_MAINTENANCE.value,
    }

    service = RentalService(repo, fleet, NoOpEventPublisher())

    with pytest.raises(ConflictError, match="under_maintenance"):
        service.register_rental(RentalCreate(car_id=1, customer_name="Alice"))


def test_register_heals_orphan_in_use_then_claims():
    """in_use with no ongoing rental (failed compensate/timeout) → release then claim."""
    repo = MagicMock()
    repo.has_ongoing_for_car.return_value = False
    created = _rental(10)
    repo.add.return_value = created
    repo.count_ongoing.return_value = 1

    fleet = MagicMock()
    fleet.get_car.return_value = {"id": 1, "status": CarStatus.IN_USE.value}
    fleet.update_car_status.side_effect = [
        {"id": 1, "status": CarStatus.AVAILABLE.value},
        {"id": 1, "status": CarStatus.IN_USE.value},
    ]

    service = RentalService(repo, fleet, NoOpEventPublisher())
    result = service.register_rental(RentalCreate(car_id=1, customer_name="Alice"))

    assert result.id == 10
    assert fleet.update_car_status.call_args_list == [
        call(1, CarStatus.AVAILABLE, expected_status=CarStatus.IN_USE),
        call(1, CarStatus.IN_USE, expected_status=CarStatus.AVAILABLE),
    ]


def test_register_rejects_in_use_when_another_rental_owns_it():
    repo = MagicMock()
    # First check at start; second inside orphan heal — both see ongoing.
    repo.has_ongoing_for_car.return_value = True
    fleet = MagicMock()

    service = RentalService(repo, fleet, NoOpEventPublisher())

    with pytest.raises(ConflictError, match="already has an ongoing rental"):
        service.register_rental(RentalCreate(car_id=1, customer_name="Alice"))

    fleet.get_car.assert_not_called()


def test_list_rentals_returns_all_when_no_filter():
    repo = MagicMock()
    repo.list.return_value = [_rental(1), _rental(2, ended=True)]
    service = RentalService(repo, MagicMock(), NoOpEventPublisher())

    result = service.list_rentals()

    assert len(result) == 2
    repo.list.assert_called_once_with(ongoing=None)


def test_list_rentals_filters_ongoing():
    repo = MagicMock()
    repo.list.return_value = [_rental(1)]
    service = RentalService(repo, MagicMock(), NoOpEventPublisher())

    result = service.list_rentals(ongoing=True)

    assert len(result) == 1
    assert result[0].end_date is None
    repo.list.assert_called_once_with(ongoing=True)


def test_list_rentals_filters_ended():
    repo = MagicMock()
    repo.list.return_value = [_rental(2, ended=True)]
    service = RentalService(repo, MagicMock(), NoOpEventPublisher())

    result = service.list_rentals(ongoing=False)

    assert len(result) == 1
    assert result[0].end_date is not None
    repo.list.assert_called_once_with(ongoing=False)


def test_register_rental_marks_car_in_use():
    repo = MagicMock()
    repo.has_ongoing_for_car.return_value = False
    created = _rental(10)
    repo.add.return_value = created
    repo.count_ongoing.return_value = 1

    fleet = MagicMock()
    fleet.get_car.return_value = {"id": 1, "status": CarStatus.AVAILABLE.value}
    fleet.update_car_status.return_value = {"id": 1, "status": CarStatus.IN_USE.value}

    service = RentalService(repo, fleet, NoOpEventPublisher())
    result = service.register_rental(RentalCreate(car_id=1, customer_name="Alice"))

    assert result.id == 10
    fleet.update_car_status.assert_called_once_with(
        1, CarStatus.IN_USE, expected_status=CarStatus.AVAILABLE
    )


def test_end_rental_restores_available():
    repo = MagicMock()
    rental = _rental(10)
    repo.get_by_id_for_update.return_value = rental
    repo.save.side_effect = lambda r: r
    repo.count_ongoing.return_value = 0

    fleet = MagicMock()
    service = RentalService(repo, fleet, NoOpEventPublisher())
    result = service.end_rental(10)

    assert result.rental.end_date is not None
    assert result.car_release.value == "restored_available"
    repo.get_by_id_for_update.assert_called_once_with(10)
    fleet.update_car_status.assert_called_once_with(
        1, CarStatus.AVAILABLE, expected_status=CarStatus.IN_USE
    )


def test_end_rental_concurrent_loser_sees_already_ended():
    """After FOR UPDATE, second ender observes end_date and skips fleet."""
    repo = MagicMock()
    repo.get_by_id_for_update.return_value = _rental(10, ended=True)
    fleet = MagicMock()
    service = RentalService(repo, fleet, NoOpEventPublisher())

    with pytest.raises(ConflictError, match="already ended"):
        service.end_rental(10)

    fleet.update_car_status.assert_not_called()
    repo.save.assert_not_called()


def test_end_rental_closes_when_car_already_deleted_from_fleet():
    """Orphan rental: fleet car is gone — still set end_date."""
    repo = MagicMock()
    rental = _rental(6, car_id=2)
    repo.get_by_id_for_update.return_value = rental
    repo.save.side_effect = lambda r: r
    repo.count_ongoing.return_value = 0

    fleet = MagicMock()
    fleet.update_car_status.side_effect = NotFoundError("Car 2 not found in fleet service")

    service = RentalService(repo, fleet, NoOpEventPublisher())
    result = service.end_rental(6)

    assert result.rental.end_date is not None
    assert result.car_release.value == "car_missing"
    repo.save.assert_called_once()


def test_end_rental_heals_when_car_already_available():
    """Desync: fleet available + ongoing rental (failed compensate) — still close."""
    repo = MagicMock()
    rental = _rental(10)
    repo.get_by_id_for_update.return_value = rental
    repo.save.side_effect = lambda r: r
    repo.count_ongoing.return_value = 0

    fleet = MagicMock()
    fleet.update_car_status.side_effect = ConflictError("expected in_use")
    fleet.get_car.return_value = {"id": 1, "status": CarStatus.AVAILABLE.value}

    service = RentalService(repo, fleet, NoOpEventPublisher())
    result = service.end_rental(10)

    assert result.rental.end_date is not None
    assert result.car_release.value == "already_available"
    repo.save.assert_called_once()
    fleet.get_car.assert_called_once_with(1)


def test_end_rental_rejects_when_car_still_unexpectedly_in_use_after_cas_conflict():
    """CAS conflict then re-read shows in_use (race) — do not close rental."""
    repo = MagicMock()
    rental = _rental(10)
    repo.get_by_id_for_update.return_value = rental

    fleet = MagicMock()
    fleet.update_car_status.side_effect = ConflictError("expected in_use")
    fleet.get_car.return_value = {"id": 1, "status": CarStatus.IN_USE.value}

    service = RentalService(repo, fleet, NoOpEventPublisher())

    with pytest.raises(ConflictError, match="status is 'in_use'"):
        service.end_rental(10)

    repo.save.assert_not_called()


def test_register_compensates_when_insert_fails():
    """Fleet CAS to in_use, then DB insert fails → compensate car back to available."""
    repo = MagicMock()
    repo.has_ongoing_for_car.return_value = False
    repo.add.side_effect = RuntimeError("db write failed")

    fleet = MagicMock()
    fleet.get_car.return_value = {"id": 1, "status": CarStatus.AVAILABLE.value}

    service = RentalService(repo, fleet, NoOpEventPublisher())

    with pytest.raises(RuntimeError, match="db write failed"):
        service.register_rental(RentalCreate(car_id=1, customer_name="Alice"))

    assert fleet.update_car_status.call_args_list == [
        call(1, CarStatus.IN_USE, expected_status=CarStatus.AVAILABLE),
        call(1, CarStatus.AVAILABLE, expected_status=CarStatus.IN_USE),
    ]


def test_register_concurrent_cas_conflict():
    """Loser of concurrent register: fleet CAS 409 → ConflictError; no rental insert."""
    repo = MagicMock()
    repo.has_ongoing_for_car.return_value = False

    fleet = MagicMock()
    fleet.get_car.return_value = {"id": 1, "status": CarStatus.AVAILABLE.value}
    fleet.update_car_status.side_effect = ConflictError("already claimed")

    service = RentalService(repo, fleet, NoOpEventPublisher())

    with pytest.raises(ConflictError, match="already claimed"):
        service.register_rental(RentalCreate(car_id=1, customer_name="Alice"))

    repo.add.assert_not_called()


def test_register_concurrent_integrity_error_is_conflict_without_compensate():
    """Unique index loss after CAS: other rental owns car — do not free it."""
    repo = MagicMock()
    # Pre-check false; post-IntegrityError check true (winner inserted).
    repo.has_ongoing_for_car.side_effect = [False, True]
    repo.add.side_effect = IntegrityError("INSERT", {}, Exception("unique"))

    fleet = MagicMock()
    fleet.get_car.return_value = {"id": 1, "status": CarStatus.AVAILABLE.value}

    service = RentalService(repo, fleet, NoOpEventPublisher())

    with pytest.raises(ConflictError, match="already has an ongoing rental"):
        service.register_rental(RentalCreate(car_id=1, customer_name="Alice"))

    fleet.update_car_status.assert_called_once_with(
        1, CarStatus.IN_USE, expected_status=CarStatus.AVAILABLE
    )


def test_register_integrity_error_compensates_when_no_other_rental():
    """IntegrityError but no ongoing row — reverse our CAS so car is not stuck."""
    repo = MagicMock()
    repo.has_ongoing_for_car.side_effect = [False, False]
    repo.add.side_effect = IntegrityError("INSERT", {}, Exception("unique"))

    fleet = MagicMock()
    fleet.get_car.return_value = {"id": 1, "status": CarStatus.AVAILABLE.value}

    service = RentalService(repo, fleet, NoOpEventPublisher())

    with pytest.raises(ConflictError, match="already has an ongoing rental"):
        service.register_rental(RentalCreate(car_id=1, customer_name="Alice"))

    assert fleet.update_car_status.call_args_list == [
        call(1, CarStatus.IN_USE, expected_status=CarStatus.AVAILABLE),
        call(1, CarStatus.AVAILABLE, expected_status=CarStatus.IN_USE),
    ]


def test_compensate_retries_transient_fleet_errors():
    """Compensation retries before succeeding (reduces permanent desync)."""
    repo = MagicMock()
    repo.has_ongoing_for_car.return_value = False
    repo.add.side_effect = RuntimeError("db write failed")

    fleet = MagicMock()
    fleet.get_car.return_value = {"id": 1, "status": CarStatus.AVAILABLE.value}
    fleet.update_car_status.side_effect = [
        {"id": 1, "status": CarStatus.IN_USE.value},  # claim
        FleetServiceError("blip"),
        FleetServiceError("blip"),
        {"id": 1, "status": CarStatus.AVAILABLE.value},  # compensate ok
    ]

    service = RentalService(repo, fleet, NoOpEventPublisher())

    with pytest.raises(RuntimeError, match="db write failed"):
        service.register_rental(RentalCreate(car_id=1, customer_name="Alice"))

    assert fleet.update_car_status.call_count == 4


def test_end_aborts_when_fleet_restore_fails():
    """Fleet CAS fails before DB write — rental stays open."""
    repo = MagicMock()
    rental = _rental(10)
    repo.get_by_id_for_update.return_value = rental

    fleet = MagicMock()
    fleet.update_car_status.side_effect = FleetServiceError("fleet down")

    service = RentalService(repo, fleet, NoOpEventPublisher())

    with pytest.raises(FleetServiceError, match="fleet down"):
        service.end_rental(10)

    repo.save.assert_not_called()
    assert rental.end_date is None


def test_end_compensates_when_persist_fails_after_fleet():
    """Fleet restored available, then DB save fails → compensate car back to in_use."""
    repo = MagicMock()
    rental = _rental(10)
    repo.get_by_id_for_update.return_value = rental
    repo.save.side_effect = RuntimeError("db write failed")

    fleet = MagicMock()
    service = RentalService(repo, fleet, NoOpEventPublisher())

    with pytest.raises(RuntimeError, match="db write failed"):
        service.end_rental(10)

    assert fleet.update_car_status.call_args_list == [
        call(1, CarStatus.AVAILABLE, expected_status=CarStatus.IN_USE),
        call(1, CarStatus.IN_USE, expected_status=CarStatus.AVAILABLE),
    ]
