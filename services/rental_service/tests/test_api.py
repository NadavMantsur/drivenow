from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from app.api.deps import get_rental_service
from app.domain.events import NoOpEventPublisher
from app.repositories.models import RentalModel
from app.services.rental_service import RentalService


@pytest.fixture
def client():
    with patch("app.main.init_db"), patch("app.main.setup_logging"):
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
        repo.has_ongoing_for_car.return_value = False
        repo.add.return_value = rental
        repo.count_ongoing.return_value = 1
        fleet.get_car.return_value = {"id": 1, "status": "available"}
        fleet.update_car_status.return_value = {"id": 1, "status": "in_use"}

        service = RentalService(repo, fleet, NoOpEventPublisher())
        app.dependency_overrides[get_rental_service] = lambda: service
        with TestClient(app) as test_client:
            yield test_client
        app.dependency_overrides.clear()


def test_health(client):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["service"] == "rental-service"


def test_register_rental_api(client):
    response = client.post("/rentals", json={"car_id": 1, "customer_name": "Bob"})
    assert response.status_code == 201
    assert response.json()["customer_name"] == "Bob"
