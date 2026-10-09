from datetime import datetime

from pydantic import BaseModel, ConfigDict


class ServiceRequestRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    source_id: str | None
    nature: str
    category: str

    location_type: str | None
    street: str | None
    intersection_1: str | None
    intersection_2: str | None
    location_error: str | None

    borough: str | None
    geographic_borough: str | None
    postal_code: str | None

    created_at: datetime
    original_channel: str | None
    responsible_unit: str | None

    longitude: float | None
    latitude: float | None

    last_status: str | None
    last_status_at: datetime | None


class ServiceRequestPage(BaseModel):
    items: list[ServiceRequestRead]
    next_after_id: int | None
    has_more: bool