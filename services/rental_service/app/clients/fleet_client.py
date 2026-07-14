from abc import ABC, abstractmethod

import httpx
from pydantic import ValidationError

from drivenow_shared.enums import CarStatus

from app.domain.exceptions import ConflictError, FleetServiceError, NotFoundError
from app.schemas.fleet import FleetCar


def _parse_fleet_car(data: object, *, car_id: int) -> FleetCar:
    try:
        return FleetCar.model_validate(data)
    except ValidationError as exc:
        raise FleetServiceError(
            f"Unexpected fleet car payload for car {car_id}: {exc}"
        ) from exc


class FleetClient(ABC):
    @abstractmethod
    def get_car(self, car_id: int) -> FleetCar:
        raise NotImplementedError

    @abstractmethod
    def update_car_status(
        self,
        car_id: int,
        status: CarStatus,
        *,
        expected_status: CarStatus | None = None,
    ) -> FleetCar:
        raise NotImplementedError


class HttpFleetClient(FleetClient):
    def __init__(
        self,
        base_url: str,
        *,
        timeout: float = 5.0,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout

    def get_car(self, car_id: int) -> FleetCar:
        try:
            response = httpx.get(f"{self._base_url}/cars/{car_id}", timeout=self._timeout)
        except httpx.HTTPError as exc:
            raise FleetServiceError(f"Fleet service unavailable: {exc}") from exc

        if response.status_code == 404:
            raise NotFoundError(f"Car {car_id} not found in fleet service")
        if response.status_code >= 400:
            raise FleetServiceError(f"Fleet service error: {response.text}")
        return _parse_fleet_car(response.json(), car_id=car_id)

    def update_car_status(
        self,
        car_id: int,
        status: CarStatus,
        *,
        expected_status: CarStatus | None = None,
    ) -> FleetCar:
        body: dict[str, str] = {"status": status.value}
        if expected_status is not None:
            body["expected_status"] = expected_status.value

        try:
            response = httpx.patch(
                f"{self._base_url}/cars/{car_id}/status",
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
        data = response.json()
        # Fleet mutation endpoints return {message, car}; keep a flat car for callers.
        if isinstance(data, dict) and "car" in data:
            data = data["car"]
        return _parse_fleet_car(data, car_id=car_id)
