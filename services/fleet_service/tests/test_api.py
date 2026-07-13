from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from drivenow_shared.enums import CarStatus

from app.api.deps import get_car_service
from app.domain.events import NoOpEventPublisher
from app.domain.status_strategy import CarStatusStrategy
from app.repositories.models import CarModel
from app.services.car_service import CarService


@pytest.fixture
def client():
    with patch("app.main.init_db"), patch("app.main.setup_logging"):
        from app.main import create_app

        app = create_app()
        repo = MagicMock()
        car = CarModel(id=1, model="Civic", year=2022, status=CarStatus.AVAILABLE)
        repo.add.return_value = car
        repo.list.return_value = [car]
        repo.get_by_id.return_value = car
        repo.count_by_status.return_value = 1
        service = CarService(repo, CarStatusStrategy(), NoOpEventPublisher())

        app.dependency_overrides[get_car_service] = lambda: service
        with TestClient(app) as test_client:
            yield test_client
        app.dependency_overrides.clear()


def test_health(client):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["service"] == "fleet-service"


def test_add_car_api(client):
    response = client.post("/cars", json={"model": "Civic", "year": 2022})
    assert response.status_code == 201
    body = response.json()
    assert body["message"] == "Car 1 was added successfully."
    assert body["car"]["model"] == "Civic"
    assert body["car"]["status"] == "available"


def test_delete_car_api(client):
    response = client.delete("/cars/1")
    assert response.status_code == 200
    assert response.json()["message"] == "Car 1 was deleted successfully."


def test_delete_car_in_use_conflict_api():
    with patch("app.main.init_db"), patch("app.main.setup_logging"):
        from app.main import create_app

        app = create_app()
        repo = MagicMock()
        repo.get_by_id_for_update.return_value = CarModel(
            id=1, model="Civic", year=2022, status=CarStatus.IN_USE
        )
        repo.count_by_status.return_value = 1
        service = CarService(repo, CarStatusStrategy(), NoOpEventPublisher())
        app.dependency_overrides[get_car_service] = lambda: service
        with TestClient(app) as test_client:
            response = test_client.delete("/cars/1")
        app.dependency_overrides.clear()

    assert response.status_code == 409
    assert "in use" in response.json()["detail"]
