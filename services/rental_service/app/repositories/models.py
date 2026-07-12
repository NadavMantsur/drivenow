from datetime import datetime

from sqlalchemy import DateTime, Index, Integer, String, text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class RentalModel(Base):
    __tablename__ = "rentals"
    __table_args__ = (
        # One ongoing rental per car — closes the concurrent double-rent race at the DB.
        Index(
            "uq_rentals_one_ongoing_per_car",
            "car_id",
            unique=True,
            postgresql_where=text("end_date IS NULL"),
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    car_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    customer_name: Mapped[str] = mapped_column(String(200), nullable=False)
    start_date: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    end_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
