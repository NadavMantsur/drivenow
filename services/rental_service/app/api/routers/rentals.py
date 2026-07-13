from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.api.deps import get_rental_service
from app.domain.exceptions import ConflictError, DomainError, FleetServiceError, NotFoundError
from app.schemas.rental import RentalCreate, RentalRead
from app.services.rental_service import RentalService

router = APIRouter(prefix="/rentals", tags=["rentals"])


@router.post("", response_model=RentalRead, status_code=status.HTTP_201_CREATED)
def register_rental(
    payload: RentalCreate,
    service: RentalService = Depends(get_rental_service),
) -> RentalRead:
    try:
        return service.register_rental(payload)
    except NotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except ConflictError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except FleetServiceError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc
    except DomainError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@router.get("", response_model=list[RentalRead])
def list_rentals(
    ongoing: bool | None = Query(
        default=None,
        description="If true, only ongoing rentals. If false, only ended. Omit for all.",
    ),
    service: RentalService = Depends(get_rental_service),
) -> list[RentalRead]:
    return service.list_rentals(ongoing=ongoing)


@router.post("/{rental_id}/end", response_model=RentalRead)
def end_rental(
    rental_id: int,
    service: RentalService = Depends(get_rental_service),
) -> RentalRead:
    try:
        return service.end_rental(rental_id)
    except NotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except ConflictError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except FleetServiceError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc
    except DomainError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
