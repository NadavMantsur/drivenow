from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class RentalCreate(BaseModel):
    car_id: int = Field(gt=0)
    customer_name: str = Field(min_length=1, max_length=200)


class RentalRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    car_id: int
    customer_name: str
    start_date: datetime
    end_date: datetime | None


class RentalActionResponse(BaseModel):
    message: str
    rental: RentalRead
