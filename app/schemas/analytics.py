from datetime import date

from pydantic import BaseModel


class BoroughCount(BaseModel):
    borough: str | None
    records: int


class CategoryCount(BaseModel):
    category: str
    records: int


class MonthlyCount(BaseModel):
    month: date
    records: int