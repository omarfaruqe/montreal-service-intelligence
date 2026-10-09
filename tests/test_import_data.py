from datetime import datetime
from uuid import uuid4

import psycopg
import pytest

from app.db.session import engine
from app.models.service_request import ServiceRequest
from scripts.import_data import (
    COLUMNS,
    COLUMN_SQL,
    FIELD_MAP,
    calculate_sha256,
    insert_batch,
    transform_row,
)


CHECKSUM = "a" * 64


def make_row(**changes):
    """Build a CSV-shaped record with valid required fields."""
    row = {source_field: "" for source_field in FIELD_MAP.values()}

    row.update(
        {
            "ID_UNIQUE": "TEST-001",
            "NATURE": "Requete",
            "ACTI_NOM": "Nid-de-poule",
            "DDS_DATE_CREATION": "2024-01-10T09:00:00",
            "DATE_DERNIER_STATUT": "2024-01-11T10:00:00",
            "LOC_LONG": "-73.6",
            "LOC_LAT": "45.5",
        }
    )

    row.update(changes)
    return row


def unpack(record):
    return dict(zip(COLUMNS, record))


def test_valid_row_transformation():
    record = unpack(
        transform_row(
            make_row(ACTI_NOM="  Nid-de-poule  "),
            7,
            CHECKSUM,
        )
    )

    assert record["category"] == "Nid-de-poule"
    assert record["created_at"] == datetime(2024, 1, 10, 9)
    assert record["last_status_at"] == datetime(2024, 1, 11, 10)
    assert record["longitude"] == -73.6
    assert record["latitude"] == 45.5
    assert record["source_file_sha256"] == CHECKSUM
    assert record["source_row_number"] == 7


def test_information_preserves_missing_fields():
    row = make_row(
        ID_UNIQUE="",
        NATURE="Information",
        LOC_LONG="",
        LOC_LAT="",
        DATE_DERNIER_STATUT="",
    )

    record = unpack(transform_row(row, 1, CHECKSUM))

    assert record["source_id"] is None
    assert record["borough"] is None
    assert record["longitude"] is None
    assert record["latitude"] is None
    assert record["last_status"] is None
    assert record["last_status_at"] is None


@pytest.mark.parametrize(
    "field",
    ["NATURE", "ACTI_NOM", "DDS_DATE_CREATION"],
)
def test_missing_required_field_is_rejected(field):
    row = make_row(**{field: " "})

    with pytest.raises(ValueError, match="Required field"):
        transform_row(row, 1, CHECKSUM)


@pytest.mark.parametrize(
    "value",
    [
        "not-a-date",
        "2024-01-10T09:00:00+00:00",
    ],
)
def test_invalid_creation_date_is_rejected(value):
    row = make_row(DDS_DATE_CREATION=value)

    with pytest.raises(ValueError):
        transform_row(row, 1, CHECKSUM)


@pytest.mark.parametrize(
    "field, value",
    [
        ("LOC_LAT", "91"),
        ("LOC_LONG", "-181"),
        ("LOC_LAT", "nan"),
        ("LOC_LONG", "inf"),
    ],
)
def test_invalid_coordinate_is_rejected(field, value):
    row = make_row(**{field: value})

    with pytest.raises(ValueError, match="Invalid"):
        transform_row(row, 1, CHECKSUM)


@pytest.mark.parametrize("extra_fields", [False, True])
def test_malformed_csv_row_is_rejected(extra_fields):
    row = make_row()

    if extra_fields:
        row[None] = ["unexpected extra value"]
    else:
        row["NATURE"] = None

    with pytest.raises(ValueError, match="number of fields"):
        transform_row(row, 1, CHECKSUM)


def test_checksum_changes_when_file_changes(tmp_path):
    source = tmp_path / "sample.csv"
    source.write_text("first version", encoding="utf-8")

    original = calculate_sha256(source)

    assert len(original) == 64
    assert calculate_sha256(source) == original

    source.write_text("revised version", encoding="utf-8")

    assert calculate_sha256(source) != original


@pytest.fixture
def import_connection():
    """Provide an isolated table and the real Psycopg connection."""
    schema = f"test_import_{uuid4().hex}"

    with engine.connect() as connection:
        transaction = connection.begin()

        try:
            connection.exec_driver_sql(f'CREATE SCHEMA "{schema}"')
            connection.exec_driver_sql(
                f'SET LOCAL search_path TO "{schema}"'
            )

            ServiceRequest.__table__.create(
                bind=connection,
                checkfirst=False,
            )

            connection.exec_driver_sql(
                f"""
                CREATE TEMP TABLE import_stage
                ON COMMIT DROP AS
                SELECT {COLUMN_SQL}
                FROM service_requests
                WITH NO DATA
                """
            )

            yield connection.connection.driver_connection

        finally:
            transaction.rollback()


def record_count(connection):
    return connection.execute(
        "SELECT COUNT(*) FROM service_requests"
    ).fetchone()[0]


def test_same_batch_is_not_imported_twice(import_connection):
    batch = [
        transform_row(make_row(), 1, CHECKSUM),
        transform_row(make_row(ID_UNIQUE="TEST-002"), 2, CHECKSUM),
    ]

    assert insert_batch(import_connection, batch) == 2
    assert insert_batch(import_connection, batch) == 0
    assert record_count(import_connection) == 2


def test_overlapping_batches_only_insert_new_rows(import_connection):
    first = transform_row(make_row(), 1, CHECKSUM)
    second = transform_row(make_row(ID_UNIQUE="TEST-002"), 2, CHECKSUM)
    third = transform_row(make_row(ID_UNIQUE="TEST-003"), 3, CHECKSUM)

    assert insert_batch(import_connection, [first, second]) == 2
    assert insert_batch(import_connection, [second, third]) == 1
    assert record_count(import_connection) == 3


def test_failed_batch_rolls_back_and_preserves_earlier_rows(
    import_connection,
):
    first = transform_row(make_row(), 1, CHECKSUM)
    assert insert_batch(import_connection, [first]) == 1

    second = transform_row(make_row(ID_UNIQUE="TEST-002"), 2, CHECKSUM)

    # Bypass transformation to test the database constraint itself.
    invalid = list(
        transform_row(make_row(ID_UNIQUE="TEST-003"), 3, CHECKSUM)
    )
    invalid[COLUMNS.index("latitude")] = 100.0

    with pytest.raises(psycopg.errors.CheckViolation):
        insert_batch(import_connection, [second, tuple(invalid)])

    assert record_count(import_connection) == 1

    # The connection remains usable after the failed batch.
    assert insert_batch(import_connection, [second]) == 1
    assert record_count(import_connection) == 2