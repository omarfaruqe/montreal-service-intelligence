# Montréal Municipal Service Intelligence Platform

A FastAPI and PostgreSQL application for importing, browsing and
analyzing Montréal 311 records.

The application preserves service requests, information enquiries,
comments and complaints. Analytics default to service requests
(`Requete`) unless another nature is selected.

## Features

- Chunked CSV import using PostgreSQL COPY.
- Validation of required fields, timestamps and coordinates.
- Safe reruns of the same CSV snapshot.
- Filtered record browsing with cursor pagination.
- Individual record lookup.
- Borough counts, leading categories and monthly trends.
- Interactive API documentation.
- 42 automated tests covering API behavior, analytics,
  importer transformations and batch insertion.

## Technology

- Python
- FastAPI and Uvicorn
- PostgreSQL 17 in Docker
- SQLAlchemy and Psycopg
- Alembic
- Pydantic
- pytest

Exact installed Python package versions are recorded in
`requirements.txt`.

## Requirements

- Python compatible with the pinned dependencies.
- Docker Desktop, or Docker Engine with Docker Compose.
- The source CSV saved as `data/raw/requetes311.csv`.

Development and testing were performed on macOS with Python 3.14
and PostgreSQL 17.

## Setup

Run commands from the project root.

### 1. Create the virtual environment

macOS/Linux:

```bash
python3 -m venv .venv
source .venv/bin/activate
```

Windows PowerShell:

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
```

Install dependencies:

```bash
python -m pip install -r requirements.txt
```

### 2. Configure the database connection

Copy `.env.example` to `.env` and configure the database URL.

The development database is exposed on host port 5433.
The application runs on the host and connects to that port.

Keep `.env` out of version control.

### 3. Start PostgreSQL

With Docker running:

```bash
docker compose up -d db
docker compose ps
```

Wait until the database is healthy.

Verify the application connection:

```bash
python -m scripts.test_db_connection
```

### 4. Apply database migrations

```bash
python -m alembic upgrade head
python -m alembic check
```

### 5. Import the dataset

Place the downloaded source CSV at:

```text
data/raw/requetes311.csv
```

Run:

```bash
python -m scripts.import_data
```

The importer:

1. Calculates the file's SHA-256 checksum.
2. Refuses to mix a different snapshot with existing imported data.
3. Validates and transforms each record.
4. Imports batches of 25,000 records.
5. Commits each successful batch.
6. Verifies the database count against the source count.
7. Writes `data/processed/import_report.json`.

Keep the source CSV unchanged while importing.

If a later batch fails, earlier committed batches remain saved.
Rerunning the same file skips rows already imported.

### 6. Start the API

```bash
python -m uvicorn app.main:app --reload
```

Open:

- Swagger UI: http://127.0.0.1:8000/docs
- Health endpoint: http://127.0.0.1:8000/health

The health endpoint reports application responsiveness;
it does not check database connectivity.

## Verified Dataset Snapshot

The imported snapshot contains 3,218,946 records:

| Nature | Records |
|---|---:|
| Requete | 1,695,602 |
| Information | 1,465,254 |
| Commentaire | 29,527 |
| Plainte | 28,563 |

These totals describe the verified local snapshot, not every
future download.

The source CSV contains 29 columns. The importer stores the
selected fields defined in `scripts/import_data.py`; additional
channel indicators and projected coordinates remain in the raw CSV.

Retain the import report to identify the snapshot by its checksum.

## Database Design

The `service_requests` table contains:

- A generated database primary key, `id`.
- A nullable source identifier, `source_id`.
- Record nature and service category.
- Location descriptions and borough fields.
- Creation timestamp.
- Original contact channel and responsible unit.
- Longitude and latitude.
- Last status and its timestamp.
- Source file checksum and source row number.
- Import timestamp.

The source identifier is not used as the primary key and has
no uniqueness constraint.

A unique index on `(source_file_sha256, source_row_number)`
prevents duplicate imports of the same file row.

Coordinate constraints enforce valid latitude and longitude ranges.
Indexes support source-ID lookup and date-based filtering by
nature, borough and category.

`borough` and `geographic_borough` are stored separately because
the source distinguishes them.

## API Endpoints

| Method | Endpoint | Purpose |
|---|---|---|
| GET | `/health` | Application health |
| GET | `/api/service-requests` | Filtered record browsing |
| GET | `/api/service-requests/{request_id}` | Lookup by database ID |
| GET | `/api/analytics/boroughs` | Counts by borough |
| GET | `/api/analytics/categories` | Leading categories |
| GET | `/api/analytics/monthly` | Counts by creation month |

### Record browsing

Supported query parameters:

- `nature`: Requete, Information, Commentaire or Plainte.
- `borough`: exact match.
- `category`: exact match.
- `last_status`: exact match.
- `created_from`: inclusive creation timestamp.
- `created_before`: exclusive creation timestamp.
- `after_id`: return IDs greater than this value; default 0.
- `limit`: page size, 1–200; default 50.

Example:

```bash
curl -sS --get \
  "http://127.0.0.1:8000/api/service-requests" \
  --data-urlencode "nature=Requete" \
  --data-urlencode "category=Nid-de-poule" \
  --data-urlencode "limit=2"
```

Responses contain:

```json
{
  "items": [],
  "next_after_id": null,
  "has_more": false
}
```

When `has_more` is true, send `next_after_id` as `after_id`
for the next page, keeping the same filters.

Results are ordered by database ID, not by creation timestamp.
Pagination does not provide a frozen snapshot if data changes
between requests.

### Analytics

All analytics endpoints accept:

- `nature`: defaults to Requete; use `all` for every nature.
- `borough`: exact match.
- `category`: exact match.
- `created_from`: inclusive.
- `created_before`: exclusive.

The categories endpoint additionally accepts `limit`, 1–100,
defaulting to 10.

Examples:

```bash
curl -sS \
  "http://127.0.0.1:8000/api/analytics/boroughs"
```

```bash
curl -sS \
  "http://127.0.0.1:8000/api/analytics/categories?limit=5"
```

```bash
curl -sS \
  "http://127.0.0.1:8000/api/analytics/monthly?nature=all"
```

Missing boroughs are returned as `null`, so those records remain
included in totals.

Monthly results include months with matching records.
An absent month is not automatically represented as zero.

Analytics return absolute record counts, not population-adjusted rates.

### Errors

- `404`: the requested database ID does not exist.
- `422`: invalid query or path parameters.

Examples include a page size above the maximum, an unsupported
nature, a malformed date or an invalid date range.

## Testing

Keep PostgreSQL running. Uvicorn is not required.

```bash
python -m pytest -q tests
```

Verified result:

```text
42 passed
```

Tests cover:

- Pagination without repeated or missing sample records.
- Combined filters and date boundaries.
- Preservation of nullable fields.
- Missing-record responses.
- Query validation.
- Borough, category and monthly aggregation.
- CSV transformations and invalid data.
- Duplicate batch prevention.
- Overlapping batches.
- Failed-batch rollback and preservation of earlier rows.

Database tests create temporary schemas inside transactions.
They roll back the schemas and sample data after each test.

The complete import orchestration and Alembic migrations do not
yet have dedicated automated tests.

## Data Interpretation and Limitations

- Missing source identifiers are preserved rather than invented.
- Source timestamps have no timezone offset. They are stored
  without assigning one; date filters must also omit offsets.
- `last_status_at` is the timestamp of the last recorded status.
  It does not, by itself, establish service resolution time.
- Borough names retain source spelling and formatting.
- Records without coordinates remain available in non-map results.
- A revised CSV snapshot is rejected to avoid double counting.
  Snapshot replacement and incremental updates are not implemented.
- Large aggregation queries may scan many rows.
  Caching and precomputed summaries are not implemented.
- The API is read-only and currently has no authentication
  or rate limiting.

## Troubleshooting

### Database connection refused on port 5433

Start Docker and PostgreSQL:

```bash
docker compose up -d db
docker compose ps
python -m scripts.test_db_connection
```

The expected port mapping is:

```text
127.0.0.1:5433->5432/tcp
```

### HTTP 500

Inspect the traceback in the Uvicorn terminal.
Verify database connectivity before changing endpoint code.

### JSON formatter reports “Expecting value”

Inspect the raw response:

```bash
curl -i \
  "http://127.0.0.1:8000/api/service-requests?limit=2"
```

The response may be plain text rather than JSON.

### Database-dependent tests fail during setup

Ensure Docker is running and PostgreSQL is healthy.
Run the database connection script, then rerun pytest.

## Development Security

- PostgreSQL is bound to the host loopback address.
- Development credentials are for local use only.
- SQLAlchemy builds parameterized endpoint queries.
- Pagination and category limits bound response sizes.
- Keep credentials and raw datasets out of Git.

A public deployment needs separate credential management,
deployment configuration and operational controls.

## AI Assistance

AI assistance was used to develop code, tests, documentation
and troubleshooting guidance. The developer ran the application,
verified import totals and executed the automated test suite.