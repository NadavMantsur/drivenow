from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from drivenow_shared.enums import CarStatus

from app.api.deps import get_car_service
from app.domain.events import NoOpEventPublisher
from app.domain.status_strategy import CarStatusStrategy
from app.repositories.models import CarModel
from app.services.car_service import CarService


def _car_service(repo: MagicMock) -> CarService:
    return CarService(repo, CarStatusStrategy(), NoOpEventPublisher())


@pytest.fixture
def client():
    with (
        patch("app.main.init_db"),
        patch("app.main.setup_logging"),
        patch("app.main.seed_metrics"),
        patch("app.api.routers.health.database_ready", return_value=True),
    ):
        from app.main import create_app

        app = create_app()
        repo = MagicMock()
        car = CarModel(id=1, model="Civic", year=2022, status=CarStatus.AVAILABLE)
        repo.add.return_value = car
        repo.list.return_value = [car]
        repo.get_by_id.return_value = car
        repo.get_by_id_for_update.return_value = car
        repo.save.side_effect = lambda c: c
        repo.count_by_status.return_value = 1
        service = _car_service(repo)

        app.dependency_overrides[get_car_service] = lambda: service
        with TestClient(app) as test_client:
            yield test_client, repo
        app.dependency_overrides.clear()


def test_health(client):
    test_client, _ = client
    response = test_client.get("/health")
    assert response.status_code == 200
    assert response.json()["service"] == "fleet-service"


def test_metrics_api(client):
    test_client, _ = client
    response = test_client.get("/metrics")
    assert response.status_code == 200
    body = response.text
    assert "drivenow_cars_available" in body
    assert "drivenow_cars_active" in body


def test_metrics_use_route_templates_not_raw_ids(client):
    """Avoid Prometheus cardinality explosion from /cars/123-style labels."""
    test_client, _ = client
    test_client.get("/cars/1")
    test_client.patch("/cars/1/status", json={"status": "under_maintenance"})
    body = test_client.get("/metrics").text

    assert 'endpoint="/cars/{car_id}"' in body
    assert 'endpoint="/cars/{car_id}/status"' in body
    assert 'endpoint="/cars/1"' not in body
    assert 'endpoint="/cars/1/status"' not in body


def test_add_car_api(client):
    test_client, _ = client
    response = test_client.post("/cars", json={"model": "Civic", "year": 2022})
    assert response.status_code == 201
    body = response.json()
    assert body["message"] == "Car 1 was added successfully."
    assert body["car"]["model"] == "Civic"
    assert body["car"]["status"] == "available"


def test_list_cars_status_filter_api(client):
    test_client, repo = client
    response = test_client.get("/cars?status=available")
    assert response.status_code == 200
    assert len(response.json()) == 1
    assert response.json()[0]["status"] == "available"
    repo.list.assert_called_with(status=CarStatus.AVAILABLE)


def test_update_car_details_api(client):
    test_client, _ = client
    response = test_client.patch(
        "/cars/1", json={"model": "Civic Hybrid", "year": 2023}
    )
    assert response.status_code == 200
    body = response.json()
    assert body["message"] == "Car 1 details were updated successfully."
    assert body["car"]["model"] == "Civic Hybrid"
    assert body["car"]["year"] == 2023
    assert body["car"]["status"] == "available"


def test_update_car_status_api(client):
    test_client, _ = client
    response = test_client.patch(
        "/cars/1/status", json={"status": "under_maintenance"}
    )
    assert response.status_code == 200
    body = response.json()
    assert "under_maintenance" in body["message"]
    assert body["car"]["status"] == "under_maintenance"


def test_cas_claim_in_use_api(client):
    test_client, repo = client
    updated = CarModel(id=1, model="Civic", year=2022, status=CarStatus.IN_USE)
    repo.transition_status.return_value = updated
    response = test_client.patch(
        "/cars/1/status",
        json={"status": "in_use", "expected_status": "available"},
    )
    assert response.status_code == 200
    assert response.json()["car"]["status"] == "in_use"
    repo.transition_status.assert_called_once_with(
        1, CarStatus.AVAILABLE, CarStatus.IN_USE
    )


def test_update_car_details_empty_body_validation(client):
    test_client, _ = client
    response = test_client.patch("/cars/1", json={})
    assert response.status_code == 422


def test_delete_car_api(client):
    test_client, _ = client
    response = test_client.delete("/cars/1")
    assert response.status_code == 200
    assert response.json()["message"] == "Car 1 was deleted successfully."


def test_delete_car_in_use_conflict_api():
    with (
        patch("app.main.init_db"),
        patch("app.main.setup_logging"),
        patch("app.main.seed_metrics"),
        patch("app.api.routers.health.database_ready", return_value=True),
    ):
        from app.main import create_app

        app = create_app()
        repo = MagicMock()
        repo.get_by_id_for_update.return_value = CarModel(
            id=1, model="Civic", year=2022, status=CarStatus.IN_USE
        )
        repo.count_by_status.return_value = 1
        service = _car_service(repo)
        app.dependency_overrides[get_car_service] = lambda: service
        with TestClient(app) as test_client:
            response = test_client.delete("/cars/1")
        app.dependency_overrides.clear()

    assert response.status_code == 409
    assert "in use" in response.json()["detail"]
