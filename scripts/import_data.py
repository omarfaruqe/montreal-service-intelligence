import csv
import hashlib
import json
import math
from datetime import datetime, timezone
from pathlib import Path

import psycopg
from sqlalchemy.engine import make_url

from app.core.config import settings


PROJECT_ROOT = Path(__file__).resolve().parents[1]
INPUT_PATH = PROJECT_ROOT / "data" / "raw" / "requetes311.csv"
REPORT_PATH = PROJECT_ROOT / "data" / "processed" / "import_report.json"

BATCH_SIZE = 25_000

# Database field -> CSV field.
FIELD_MAP = {
    "source_id": "ID_UNIQUE",
    "nature": "NATURE",
    "category": "ACTI_NOM",
    "location_type": "TYPE_LIEU_INTERV",
    "street": "RUE",
    "intersection_1": "RUE_INTERSECTION1",
    "intersection_2": "RUE_INTERSECTION2",
    "location_error": "LOC_ERREUR_GDT",
    "borough": "ARRONDISSEMENT",
    "geographic_borough": "ARRONDISSEMENT_GEO",
    "postal_code": "LIN_CODE_POSTAL",
    "created_at": "DDS_DATE_CREATION",
    "original_channel": "PROVENANCE_ORIGINALE",
    "responsible_unit": "UNITE_RESP_PARENT",
    "longitude": "LOC_LONG",
    "latitude": "LOC_LAT",
    "last_status": "DERNIER_STATUT",
    "last_status_at": "DATE_DERNIER_STATUT",
}

COLUMNS = list(FIELD_MAP) + [
    "source_file_sha256",
    "source_row_number",
]

# These names are fixed in our code, not supplied by users.
COLUMN_SQL = ", ".join(COLUMNS)


def calculate_sha256(path: Path) -> str:
    digest = hashlib.sha256()

    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(block)

    return digest.hexdigest()


def clean_text(value: str | None) -> str | None:
    if value is None:
        return None

    value = value.strip()
    return value or None


def parse_date(value: str | None, field: str) -> datetime | None:
    if value is None:
        return None

    parsed = datetime.fromisoformat(value)

    if parsed.tzinfo is not None:
        raise ValueError(
            f"{field} unexpectedly contains a timezone offset: {value}"
        )

    return parsed


def parse_coordinate(
    value: str | None,
    field: str,
    minimum: float,
    maximum: float,
) -> float | None:
    if value is None:
        return None

    parsed = float(value)

    if not math.isfinite(parsed) or not minimum <= parsed <= maximum:
        raise ValueError(f"Invalid {field}: {value}")

    return parsed


def transform_row(
    row: dict,
    row_number: int,
    checksum: str,
) -> tuple:
    if None in row or any(value is None for value in row.values()):
        raise ValueError("CSV row has an unexpected number of fields.")

    record = {
        field: clean_text(row[source_field])
        for field, source_field in FIELD_MAP.items()
    }

    for field in ("nature", "category", "created_at"):
        if record[field] is None:
            raise ValueError(f"Required field is missing: {field}")

    record["created_at"] = parse_date(
        record["created_at"], "created_at"
    )
    record["last_status_at"] = parse_date(
        record["last_status_at"], "last_status_at"
    )

    record["longitude"] = parse_coordinate(
        record["longitude"], "longitude", -180, 180
    )
    record["latitude"] = parse_coordinate(
        record["latitude"], "latitude", -90, 90
    )

    record["source_file_sha256"] = checksum
    record["source_row_number"] = row_number

    return tuple(record[column] for column in COLUMNS)


def insert_batch(connection, batch: list[tuple]) -> int:
    # COPY and INSERT succeed or roll back together.
    with connection.transaction():
        with connection.cursor() as cursor:
            cursor.execute("TRUNCATE import_stage")

            with cursor.copy(
                f"COPY import_stage ({COLUMN_SQL}) FROM STDIN"
            ) as copy:
                for record in batch:
                    copy.write_row(record)

            cursor.execute(
                f"""
                INSERT INTO service_requests ({COLUMN_SQL})
                SELECT {COLUMN_SQL}
                FROM import_stage
                ON CONFLICT (
                    source_file_sha256,
                    source_row_number
                ) DO NOTHING
                """
            )

            return cursor.rowcount


def main() -> None:
    if not INPUT_PATH.exists():
        raise FileNotFoundError(f"Dataset not found: {INPUT_PATH}")

    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)

    print("Calculating CSV checksum...")
    checksum = calculate_sha256(INPUT_PATH)

    # Convert SQLAlchemy's URL into Psycopg connection arguments.
    url = make_url(settings.database_url)

    connection_options = {
        "host": url.host,
        "port": url.port or 5432,
        "dbname": url.database,
        "user": url.username,
        "password": url.password,
        "autocommit": True,
    }

    source_rows = 0
    inserted_rows = 0
    batch = []

    with psycopg.connect(**connection_options) as connection:
        # Prevent two copies of this importer running simultaneously.
        locked = connection.execute(
            "SELECT pg_try_advisory_lock(3112022)"
        ).fetchone()[0]

        if not locked:
            raise RuntimeError("Another import is already running.")

        # Connection closure releases the advisory lock automatically.
        other_snapshot = connection.execute(
            """
            SELECT EXISTS (
                SELECT 1
                FROM service_requests
                WHERE source_file_sha256 <> %s
            )
            """,
            (checksum,),
        ).fetchone()[0]

        if other_snapshot:
            raise RuntimeError(
                "The database contains a different CSV snapshot. "
                "Stopping to avoid double-counting revised downloads."
            )

        existing_rows = connection.execute(
            """
            SELECT COUNT(*)
            FROM service_requests
            WHERE source_file_sha256 = %s
            """,
            (checksum,),
        ).fetchone()[0]

        print(f"Previously imported rows: {existing_rows:,}")

        connection.execute(
            f"""
            CREATE TEMP TABLE import_stage AS
            SELECT {COLUMN_SQL}
            FROM service_requests
            WITH NO DATA
            """
        )

        with INPUT_PATH.open(
            "r",
            encoding="utf-8-sig",
            newline="",
        ) as source:
            reader = csv.DictReader(source)

            if not reader.fieldnames:
                raise ValueError("CSV header is missing.")

            if len(reader.fieldnames) != len(set(reader.fieldnames)):
                raise ValueError("CSV contains duplicate column names.")

            missing_columns = (
                set(FIELD_MAP.values()) - set(reader.fieldnames)
            )

            if missing_columns:
                raise ValueError(
                    f"CSV columns missing: {sorted(missing_columns)}"
                )

            for source_rows, row in enumerate(reader, start=1):
                try:
                    batch.append(
                        transform_row(row, source_rows, checksum)
                    )
                except (ValueError, KeyError) as error:
                    raise ValueError(
                        f"Invalid CSV data record {source_rows}: {error}. "
                        "Earlier committed batches remain saved."
                    ) from error

                if len(batch) >= BATCH_SIZE:
                    inserted_rows += insert_batch(connection, batch)
                    batch.clear()

                    print(
                        f"Processed {source_rows:,} records | "
                        f"Inserted this run: {inserted_rows:,}",
                        flush=True,
                    )

            if batch:
                inserted_rows += insert_batch(connection, batch)

        database_rows = connection.execute(
            """
            SELECT COUNT(*)
            FROM service_requests
            WHERE source_file_sha256 = %s
            """,
            (checksum,),
        ).fetchone()[0]

        if database_rows != source_rows:
            raise RuntimeError(
                f"Count mismatch: CSV={source_rows:,}, "
                f"database={database_rows:,}"
            )

        summary_rows = connection.execute(
            """
            SELECT
                nature,
                COUNT(*) AS total,
                COUNT(*) FILTER (
                    WHERE source_id IS NULL
                ) AS missing_source_ids,
                COUNT(*) FILTER (
                    WHERE borough IS NULL
                ) AS missing_boroughs
            FROM service_requests
            WHERE source_file_sha256 = %s
            GROUP BY nature
            ORDER BY total DESC
            """,
            (checksum,),
        ).fetchall()

        connection.execute("ANALYZE service_requests")

    report = {
        "completed_at_utc": datetime.now(timezone.utc).isoformat(),
        "source_file": INPUT_PATH.name,
        "source_file_sha256": checksum,
        "source_rows": source_rows,
        "previously_imported_rows": existing_rows,
        "inserted_this_run": inserted_rows,
        "already_present_rows": source_rows - inserted_rows,
        "database_rows": database_rows,
        "counts_match": database_rows == source_rows,
        "by_nature": [
            {
                "nature": nature,
                "total": total,
                "missing_source_ids": missing_ids,
                "missing_boroughs": missing_boroughs,
            }
            for nature, total, missing_ids, missing_boroughs
            in summary_rows
        ],
    }

    REPORT_PATH.write_text(
        json.dumps(report, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )

    print("\nImport completed. Validation passed.")
    print(json.dumps(report, indent=2, ensure_ascii=False))
    print(f"\nSaved report: {REPORT_PATH}")


if __name__ == "__main__":
    main()