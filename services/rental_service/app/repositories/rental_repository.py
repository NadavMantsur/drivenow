from abc import ABC, abstractmethod

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.repositories.models import RentalModel


class RentalRepository(ABC):
    @abstractmethod
    def add(self, rental: RentalModel) -> RentalModel:
        raise NotImplementedError

    @abstractmethod
    def get_by_id(self, rental_id: int) -> RentalModel | None:
        raise NotImplementedError

    @abstractmethod
    def save(self, rental: RentalModel) -> RentalModel:
        raise NotImplementedError

    @abstractmethod
    def count_ongoing(self) -> int:
        raise NotImplementedError

    @abstractmethod
    def has_ongoing_for_car(self, car_id: int) -> bool:
        raise NotImplementedError

    @abstractmethod
    def list(self, *, ongoing: bool | None = None) -> list[RentalModel]:
        raise NotImplementedError


class SqlAlchemyRentalRepository(RentalRepository):
    def __init__(self, db: Session) -> None:
        self._db = db

    def add(self, rental: RentalModel) -> RentalModel:
        self._db.add(rental)
        self._db.commit()
        self._db.refresh(rental)
        return rental

    def get_by_id(self, rental_id: int) -> RentalModel | None:
        return self._db.get(RentalModel, rental_id)

    def save(self, rental: RentalModel) -> RentalModel:
        self._db.add(rental)
        self._db.commit()
        self._db.refresh(rental)
        return rental

    def count_ongoing(self) -> int:
        stmt = select(RentalModel).where(RentalModel.end_date.is_(None))
        return len(list(self._db.scalars(stmt).all()))

    def has_ongoing_for_car(self, car_id: int) -> bool:
        stmt = select(RentalModel).where(
            RentalModel.car_id == car_id,
            RentalModel.end_date.is_(None),
        )
        return self._db.scalars(stmt).first() is not None

    def list(self, *, ongoing: bool | None = None) -> list[RentalModel]:
        stmt = select(RentalModel).order_by(RentalModel.id)
        if ongoing is True:
            stmt = stmt.where(RentalModel.end_date.is_(None))
        elif ongoing is False:
            stmt = stmt.where(RentalModel.end_date.is_not(None))
        return list(self._db.scalars(stmt).all())
