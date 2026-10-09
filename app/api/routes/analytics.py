from datetime import datetime
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.service_request import ServiceRequest
from app.schemas.analytics import (
    BoroughCount,
    CategoryCount,
    MonthlyCount,
)


router = APIRouter(
    prefix="/analytics",
    tags=["Analytics"],
)

DatabaseSession = Annotated[Session, Depends(get_db)]

NatureFilter = Literal[
    "Requete",
    "Information",
    "Commentaire",
    "Plainte",
    "all",
]


def analytics_filters(
    nature: NatureFilter = "Requete",
    borough: Annotated[
        str | None, Query(min_length=1, max_length=200)
    ] = None,
    category: Annotated[
        str | None, Query(min_length=1, max_length=300)
    ] = None,
    created_from: datetime | None = None,
    created_before: datetime | None = None,
):
    for field, value in (
        ("created_from", created_from),
        ("created_before", created_before),
    ):
        if value is not None and value.tzinfo is not None:
            raise HTTPException(
                status_code=422,
                detail=f"{field} must not contain a timezone offset.",
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

    conditions = []

    if nature != "all":
        conditions.append(ServiceRequest.nature == nature)

    if borough is not None:
        conditions.append(ServiceRequest.borough == borough)

    if category is not None:
        conditions.append(ServiceRequest.category == category)

    if created_from is not None:
        conditions.append(ServiceRequest.created_at >= created_from)

    if created_before is not None:
        conditions.append(ServiceRequest.created_at < created_before)

    return conditions


Filters = Annotated[list, Depends(analytics_filters)]


@router.get("/boroughs", response_model=list[BoroughCount])
def counts_by_borough(
    db: DatabaseSession,
    filters: Filters,
):
    count = func.count().label("records")

    statement = (
        select(ServiceRequest.borough, count)
        .where(*filters)
        .group_by(ServiceRequest.borough)
        .order_by(
            count.desc(),
            ServiceRequest.borough.asc().nulls_last(),
        )
    )

    return [
        BoroughCount(borough=borough, records=records)
        for borough, records in db.execute(statement)
    ]


@router.get("/categories", response_model=list[CategoryCount])
def top_categories(
    db: DatabaseSession,
    filters: Filters,
    limit: Annotated[int, Query(ge=1, le=100)] = 10,
):
    count = func.count().label("records")

    statement = (
        select(ServiceRequest.category, count)
        .where(*filters)
        .group_by(ServiceRequest.category)
        .order_by(count.desc(), ServiceRequest.category.asc())
        .limit(limit)
    )

    return [
        CategoryCount(category=category, records=records)
        for category, records in db.execute(statement)
    ]


@router.get("/monthly", response_model=list[MonthlyCount])
def monthly_counts(
    db: DatabaseSession,
    filters: Filters,
):
    month = func.date_trunc(
        "month", ServiceRequest.created_at
    ).label("month")

    statement = (
        select(month, func.count().label("records"))
        .where(*filters)
        .group_by(month)
        .order_by(month)
    )

    return [
        MonthlyCount(month=month.date(), records=records)
        for month, records in db.execute(statement)
    ]