from fastapi import APIRouter, Depends, HTTPException, Query, status

from drivenow_shared.enums import CarStatus

from app.api.deps import get_car_service
from app.domain.exceptions import (
    ConflictError,
    DomainError,
    InvalidStatusTransitionError,
    NotFoundError,
)
from app.schemas.car import CarCreate, CarRead, CarUpdate
from app.services.car_service import CarService

router = APIRouter(prefix="/cars", tags=["cars"])


@router.post("", response_model=CarRead, status_code=status.HTTP_201_CREATED)
def add_car(payload: CarCreate, service: CarService = Depends(get_car_service)) -> CarRead:
    try:
        return service.add_car(payload)
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


@router.patch("/{car_id}", response_model=CarRead)
def update_car(
    car_id: int,
    payload: CarUpdate,
    service: CarService = Depends(get_car_service),
) -> CarRead:
    try:
        return service.update_car(car_id, payload)
    except NotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except (InvalidStatusTransitionError, ConflictError) as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except DomainError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
