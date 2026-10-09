from datetime import datetime
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Path, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.service_request import ServiceRequest
from app.schemas.service_request import (
    ServiceRequestPage,
    ServiceRequestRead,
)


router = APIRouter(
    prefix="/service-requests",
    tags=["Service requests"],
)

DatabaseSession = Annotated[Session, Depends(get_db)]
Nature = Literal["Requete", "Information", "Commentaire", "Plainte"]


@router.get("", response_model=ServiceRequestPage)
def list_service_requests(
    db: DatabaseSession,
    nature: Nature | None = None,
    borough: Annotated[
        str | None, Query(min_length=1, max_length=200)
    ] = None,
    category: Annotated[
        str | None, Query(min_length=1, max_length=300)
    ] = None,
    last_status: Annotated[
        str | None, Query(min_length=1, max_length=100)
    ] = None,
    created_from: datetime | None = None,
    created_before: datetime | None = None,
    after_id: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
):
    for field, value in (
        ("created_from", created_from),
        ("created_before", created_before),
    ):
        if value is not None and value.tzinfo is not None:
            raise HTTPException(
                status_code=422,
                detail=(
                    f"{field} must not contain a timezone offset, "
                    "because the source timestamps have none."
                ),
            )

    if (
        created_from is not None
        and created_before is not None
        and created_from >= created_before
    ):
        raise HTTPException(
            status_code=422,
            detail="created_from must be earlier than created_before.",
        )

    statement = select(ServiceRequest).where(
        ServiceRequest.id > after_id
    )

    for column, value in (
        (ServiceRequest.nature, nature),
        (ServiceRequest.borough, borough),
        (ServiceRequest.category, category),
        (ServiceRequest.last_status, last_status),
    ):
        if value is not None:
            statement = statement.where(column == value)

    if created_from is not None:
        statement = statement.where(
            ServiceRequest.created_at >= created_from
        )

    if created_before is not None:
        statement = statement.where(
            ServiceRequest.created_at < created_before
        )

    # Fetch one extra row to determine whether another page exists.
    statement = statement.order_by(ServiceRequest.id).limit(limit + 1)
    records = db.scalars(statement).all()

    has_more = len(records) > limit
    items = records[:limit]

    return ServiceRequestPage(
        items=[
            ServiceRequestRead.model_validate(record)
            for record in items
        ],
        next_after_id=items[-1].id if has_more else None,
        has_more=has_more,
    )


@router.get("/{request_id}", response_model=ServiceRequestRead)
def get_service_request(
    request_id: Annotated[int, Path(ge=1)],
    db: DatabaseSession,
):
    record = db.get(ServiceRequest, request_id)

    if record is None:
        raise HTTPException(
            status_code=404,
            detail="Service request not found.",
        )

    return record