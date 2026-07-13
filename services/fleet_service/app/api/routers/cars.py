from typing import Annotated

from fastapi import APIRouter, Body, Depends, HTTPException, Query, status

from drivenow_shared.enums import CarStatus

from app.api.deps import get_car_service
from app.domain.exceptions import (
    ConflictError,
    DomainError,
    InvalidStatusTransitionError,
    NotFoundError,
)
from app.schemas.car import (
    CarActionResponse,
    CarCreate,
    CarDetailsUpdate,
    CarRead,
    CarStatusUpdate,
    MessageResponse,
)
from app.services.car_service import CarService

router = APIRouter(prefix="/cars", tags=["cars"])

_STATUS_EXAMPLE_MAINTENANCE = {"status": "under_maintenance"}
_STATUS_EXAMPLE_AVAILABLE = {"status": "available"}
_DETAILS_EXAMPLE = {"model": "Corolla Hybrid", "year": 2025}


@router.post("", response_model=CarActionResponse, status_code=status.HTTP_201_CREATED)
def add_car(
    payload: CarCreate, service: CarService = Depends(get_car_service)
) -> CarActionResponse:
    try:
        car = service.add_car(payload)
        return CarActionResponse(
            message=f"Car {car.id} was added successfully.",
            car=car,
        )
    except DomainError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@router.get("", response_model=list[CarRead])
def list_cars(
    status_filter: CarStatus | None = Query(default=None, alias="status"),
    service: CarService = Depends(get_car_service),
) -> list[CarRead]:
    return service.list_cars(status=status_filter)


@router.get("/{car_id}", response_model=CarRead)
def get_car(car_id: int, service: CarService = Depends(get_car_service)) -> CarRead:
    try:
        return service.get_car(car_id)
    except NotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@router.patch(
    "/{car_id}",
    response_model=CarActionResponse,
    summary="Update car details",
    description="Update model and/or year only. Use PATCH /cars/{id}/status to change status.",
)
def update_car_details(
    car_id: int,
    payload: Annotated[
        CarDetailsUpdate,
        Body(
            openapi_examples={
                "update_details": {
                    "summary": "Update model and year",
                    "value": _DETAILS_EXAMPLE,
                },
            }
        ),
    ],
    service: CarService = Depends(get_car_service),
) -> CarActionResponse:
    try:
        car = service.update_car_details(car_id, payload)
        return CarActionResponse(
            message=f"Car {car.id} details were updated successfully.",
            car=car,
        )
    except NotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except DomainError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@router.patch(
    "/{car_id}/status",
    response_model=CarActionResponse,
    summary="Update car status",
    description=(
        "Change status (available / in_use / under_maintenance). "
        "While in_use, direct updates are rejected — end the rental (CAS "
        "in_use→available with expected_status) to release the car. "
        "Optional expected_status enables compare-and-set for concurrent updates."
    ),
)
def update_car_status(
    car_id: int,
    payload: Annotated[
        CarStatusUpdate,
        Body(
            openapi_examples={
                "set_maintenance": {
                    "summary": "Set under maintenance",
                    "value": _STATUS_EXAMPLE_MAINTENANCE,
                },
                "set_available": {
                    "summary": "Set available (e.g. back from maintenance)",
                    "value": _STATUS_EXAMPLE_AVAILABLE,
                },
            }
        ),
    ],
    service: CarService = Depends(get_car_service),
) -> CarActionResponse:
    try:
        result = service.update_car_status(car_id, payload)
        if result.changed:
            message = (
                f"Car {result.car.id} status was updated successfully "
                f"to '{result.car.status.value}'."
            )
        else:
            message = (
                f"Car {result.car.id} is already '{result.car.status.value}' "
                f"— no change applied."
            )
        return CarActionResponse(message=message, car=result.car)
    except NotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except (InvalidStatusTransitionError, ConflictError) as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except DomainError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@router.delete("/{car_id}", response_model=MessageResponse)
def delete_car(
    car_id: int, service: CarService = Depends(get_car_service)
) -> MessageResponse:
    try:
        service.delete_car(car_id)
        return MessageResponse(message=f"Car {car_id} was deleted successfully.")
    except NotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except ConflictError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except DomainError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
