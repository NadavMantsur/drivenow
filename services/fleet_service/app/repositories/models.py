from sqlalchemy import Enum, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from drivenow_shared.enums import CarStatus

from app.core.database import Base


class CarModel(Base):
    __tablename__ = "cars"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    model: Mapped[str] = mapped_column(String(120), nullable=False)
    year: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[CarStatus] = mapped_column(
        Enum(CarStatus, name="car_status", values_callable=lambda x: [e.value for e in x]),
        nullable=False,
        default=CarStatus.AVAILABLE,
    )
