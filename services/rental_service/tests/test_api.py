from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.deps import get_rental_service
from app.domain.events import NoOpEventPublisher
from app.core.database import Base
from app.repositories.models import RentalModel
from app.repositories.rental_repository import SqlAlchemyRentalRepository
from app.services.rental_service import RentalService


@pytest.fixture
def client():
    with (
        patch("app.main.init_db"),
        patch("app.main.setup_logging"),
        patch("app.main.seed_metrics"),
    ):
        from app.main import create_app

        app = create_app()
        repo = MagicMock()
        fleet = MagicMock()
        rental = RentalModel(
            id=1,
            car_id=1,
            customer_name="Bob",
            start_date=datetime.now(timezone.utc),
            end_date=None,
        )
        ended = RentalModel(
            id=2,
            car_id=2,
            customer_name="Alice",
            start_date=datetime.now(timezone.utc),
            end_date=datetime.now(timezone.utc),
        )
        repo.has_ongoing_for_car.return_value = False
        repo.add.return_value = rental
        repo.get_by_id.return_value = rental
        repo.save.side_effect = lambda r: r
        repo.count_ongoing.return_value = 1
        repo.list.return_value = [rental, ended]
        fleet.get_car.return_value = {"id": 1, "status": "available"}
        fleet.update_car_status.return_value = {"id": 1, "status": "in_use"}

        service = RentalService(repo, fleet, NoOpEventPublisher())
        app.dependency_overrides[get_rental_service] = lambda: service
        with TestClient(app) as test_client:
            yield test_client, repo, fleet
        app.dependency_overrides.clear()


@pytest.fixture
def rental_repo() -> SqlAlchemyRentalRepository:
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)
    db: Session = SessionLocal()
    repo = SqlAlchemyRentalRepository(db)
    yield repo
    db.close()


def test_health(client):
    test_client, _, _ = client
    response = test_client.get("/health")
    assert response.status_code == 200
    assert response.json()["service"] == "rental-service"


def test_metrics_api(client):
    test_client, _, _ = client
    response = test_client.get("/metrics")
    assert response.status_code == 200
    assert "drivenow_rentals_ongoing" in response.text


def test_register_rental_api(client):
    test_client, _, _ = client
    response = test_client.post("/rentals", json={"car_id": 1, "customer_name": "Bob"})
    assert response.status_code == 201
    body = response.json()
    assert body["message"] == "Rental 1 was registered successfully for car 1."
    assert body["rental"]["customer_name"] == "Bob"


def test_end_rental_api(client):
    test_client, repo, fleet = client
    fleet.update_car_status.return_value = {"id": 1, "status": "available"}
    response = test_client.post("/rentals/1/end")
    assert response.status_code == 200
    body = response.json()
    assert "ended successfully" in body["message"]
    assert body["rental"]["id"] == 1
    assert body["rental"]["end_date"] is not None
    fleet.update_car_status.assert_called()
    repo.save.assert_called()


def test_list_rentals_api(client):
    test_client, repo, _ = client
    response = test_client.get("/rentals")
    assert response.status_code == 200
    body = response.json()
    assert len(body) == 2
    assert {row["id"] for row in body} == {1, 2}
    repo.list.assert_called_with(ongoing=None)


def test_list_ongoing_rentals_api(client):
    test_client, repo, _ = client
    ongoing = RentalModel(
        id=1,
        car_id=1,
        customer_name="Bob",
        start_date=datetime.now(timezone.utc),
        end_date=None,
    )
    repo.list.return_value = [ongoing]
    response = test_client.get("/rentals?ongoing=true")
    assert response.status_code == 200
    assert len(response.json()) == 1
    assert response.json()[0]["end_date"] is None
    repo.list.assert_called_with(ongoing=True)


def test_list_ended_rentals_api(client):
    test_client, repo, _ = client
    ended = RentalModel(
        id=2,
        car_id=2,
        customer_name="Alice",
        start_date=datetime.now(timezone.utc),
        end_date=datetime.now(timezone.utc),
    )
    repo.list.return_value = [ended]
    response = test_client.get("/rentals?ongoing=false")
    assert response.status_code == 200
    assert len(response.json()) == 1
    assert response.json()[0]["end_date"] is not None
    repo.list.assert_called_with(ongoing=False)


def test_repository_list_filters_ongoing_and_ended(rental_repo):
    now = datetime.now(timezone.utc)
    rental_repo.add(
        RentalModel(car_id=1, customer_name="Alice", start_date=now, end_date=None)
    )
    rental_repo.add(
        RentalModel(car_id=2, customer_name="Bob", start_date=now, end_date=now)
    )

    all_rows = rental_repo.list()
    ongoing = rental_repo.list(ongoing=True)
    ended = rental_repo.list(ongoing=False)

    assert len(all_rows) == 2
    assert [r.customer_name for r in ongoing] == ["Alice"]
    assert [r.customer_name for r in ended] == ["Bob"]
