from datetime import datetime

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    Float,
    Identity,
    Index,
    String,
    Text,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class ServiceRequest(Base):
    __tablename__ = "service_requests"

    id: Mapped[int] = mapped_column(
        BigInteger,
        Identity(),
        primary_key=True,
    )

    source_id: Mapped[str | None] = mapped_column(Text)

    nature: Mapped[str] = mapped_column(Text, nullable=False)
    category: Mapped[str] = mapped_column(Text, nullable=False)

    location_type: Mapped[str | None] = mapped_column(Text)
    street: Mapped[str | None] = mapped_column(Text)
    intersection_1: Mapped[str | None] = mapped_column(Text)
    intersection_2: Mapped[str | None] = mapped_column(Text)
    location_error: Mapped[str | None] = mapped_column(Text)

    borough: Mapped[str | None] = mapped_column(Text)
    geographic_borough: Mapped[str | None] = mapped_column(Text)
    postal_code: Mapped[str | None] = mapped_column(Text)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=False),
        nullable=False,
    )

    original_channel: Mapped[str | None] = mapped_column(Text)
    responsible_unit: Mapped[str | None] = mapped_column(Text)

    longitude: Mapped[float | None] = mapped_column(Float)
    latitude: Mapped[float | None] = mapped_column(Float)

    last_status: Mapped[str | None] = mapped_column(Text)
    last_status_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=False),
    )

    # Identifies the imported file and the row within that file.
    source_file_sha256: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
    )
    source_row_number: Mapped[int] = mapped_column(
        BigInteger,
        nullable=False,
    )

    imported_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    __table_args__ = (
        CheckConstraint(
            "latitude IS NULL OR latitude BETWEEN -90 AND 90",
            name="ck_service_requests_latitude",
        ),
        CheckConstraint(
            "longitude IS NULL OR longitude BETWEEN -180 AND 180",
            name="ck_service_requests_longitude",
        ),
        CheckConstraint(
            "source_row_number > 0",
            name="ck_service_requests_source_row",
        ),
        Index("ix_service_requests_source_id", "source_id"),
        Index("ix_service_requests_created_at", "created_at"),
        Index(
            "ix_service_requests_nature_created_at",
            "nature",
            "created_at",
        ),
        Index(
            "ix_service_requests_borough_created_at",
            "borough",
            "created_at",
        ),
        Index(
            "ix_service_requests_category_created_at",
            "category",
            "created_at",
        ),
        Index(
            "ux_service_requests_source_file_row",
            "source_file_sha256",
            "source_row_number",
            unique=True,
        ),
    )