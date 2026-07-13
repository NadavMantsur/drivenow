from abc import ABC, abstractmethod

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from drivenow_shared.enums import CarStatus

from app.repositories.models import CarModel


class CarRepository(ABC):
    @abstractmethod
    def add(self, car: CarModel) -> CarModel:
        raise NotImplementedError

    @abstractmethod
    def get_by_id(self, car_id: int) -> CarModel | None:
        raise NotImplementedError

    @abstractmethod
    def get_by_id_for_update(self, car_id: int) -> CarModel | None:
        raise NotImplementedError

    @abstractmethod
    def list(self, status: CarStatus | None = None) -> list[CarModel]:
        raise NotImplementedError

    @abstractmethod
    def save(self, car: CarModel) -> CarModel:
        raise NotImplementedError

    @abstractmethod
    def delete(self, car: CarModel) -> None:
        raise NotImplementedError

    @abstractmethod
    def transition_status(
        self,
        car_id: int,
        expected_status: CarStatus,
        new_status: CarStatus,
    ) -> CarModel | None:
        """Atomic CAS: update only if current status matches expected. None = mismatch/missing."""
        raise NotImplementedError

    @abstractmethod
    def count_by_status(self, status: CarStatus) -> int:
        raise NotImplementedError


class SqlAlchemyCarRepository(CarRepository):
    def __init__(self, db: Session) -> None:
        self._db = db

    def add(self, car: CarModel) -> CarModel:
        self._db.add(car)
        self._db.commit()
        self._db.refresh(car)
        return car

    def get_by_id(self, car_id: int) -> CarModel | None:
        return self._db.get(CarModel, car_id)

    def get_by_id_for_update(self, car_id: int) -> CarModel | None:
        stmt = select(CarModel).where(CarModel.id == car_id).with_for_update()
        return self._db.scalars(stmt).first()

    def list(self, status: CarStatus | None = None) -> list[CarModel]:
        stmt = select(CarModel).order_by(CarModel.id)
        if status is not None:
            stmt = stmt.where(CarModel.status == status)
        return list(self._db.scalars(stmt).all())

    def save(self, car: CarModel) -> CarModel:
        self._db.add(car)
        self._db.commit()
        self._db.refresh(car)
        return car

    def delete(self, car: CarModel) -> None:
        self._db.delete(car)
        self._db.commit()

    def transition_status(
        self,
        car_id: int,
        expected_status: CarStatus,
        new_status: CarStatus,
    ) -> CarModel | None:
        stmt = (
            update(CarModel)
            .where(CarModel.id == car_id, CarModel.status == expected_status)
            .values(status=new_status)
        )
        result = self._db.execute(stmt)
        if result.rowcount != 1:
            self._db.rollback()
            return None
        self._db.commit()
        return self.get_by_id(car_id)

    def count_by_status(self, status: CarStatus) -> int:
        stmt = select(CarModel).where(CarModel.status == status)
        return len(list(self._db.scalars(stmt).all()))
