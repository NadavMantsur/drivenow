from abc import ABC, abstractmethod
from typing import Any

import httpx

from drivenow_shared.enums import CarStatus

from app.domain.exceptions import ConflictError, FleetServiceError, NotFoundError


class FleetClient(ABC):
    @abstractmethod
    def get_car(self, car_id: int) -> dict[str, Any]:
        raise NotImplementedError

    @abstractmethod
    def update_car_status(
        self,
        car_id: int,
        status: CarStatus,
        *,
        expected_status: CarStatus | None = None,
    ) -> dict[str, Any]:
        raise NotImplementedError


class HttpFleetClient(FleetClient):
    def __init__(self, base_url: str, timeout: float = 5.0) -> None:
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout

    def get_car(self, car_id: int) -> dict[str, Any]:
        try:
            response = httpx.get(f"{self._base_url}/cars/{car_id}", timeout=self._timeout)
        except httpx.HTTPError as exc:
            raise FleetServiceError(f"Fleet service unavailable: {exc}") from exc

        if response.status_code == 404:
            raise NotFoundError(f"Car {car_id} not found in fleet service")
        if response.status_code >= 400:
            raise FleetServiceError(f"Fleet service error: {response.text}")
        return response.json()

    def update_car_status(
        self,
        car_id: int,
        status: CarStatus,
        *,
        expected_status: CarStatus | None = None,
    ) -> dict[str, Any]:
        body: dict[str, str] = {"status": status.value}
        if expected_status is not None:
            body["expected_status"] = expected_status.value

        try:
            response = httpx.patch(
                f"{self._base_url}/cars/{car_id}",
                json=body,
                timeout=self._timeout,
            )
        except httpx.HTTPError as exc:
            raise FleetServiceError(f"Fleet service unavailable: {exc}") from exc

        if response.status_code == 404:
            raise NotFoundError(f"Car {car_id} not found in fleet service")
        if response.status_code == 409:
            raise ConflictError(f"Fleet status conflict for car {car_id}: {response.text}")
        if response.status_code >= 400:
            raise FleetServiceError(f"Fleet service error: {response.text}")
        return response.json()
