import csv
from collections import Counter
from pathlib import Path

import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[1]
INPUT_PATH = PROJECT_ROOT / "data" / "raw" / "requetes311.csv"
REPORT_PATH = PROJECT_ROOT / "data" / "raw" / "inspection_report.txt"

CHUNK_SIZE = 50_000

# Count these fields only when they exist in the downloaded file.
CATEGORY_CANDIDATES = (
    "NATURE",
    "ACTI_NOM",
    "ARRONDISSEMENT",
    "ARRONDISSEMENT_NOM",
    "ARRONDISSEMENT_GEO",
    "PROVENANCE_ORIGINALE",
    "DERNIER_STATUT",
    "STATUT",
)


def detect_format() -> tuple[str, str]:
    with INPUT_PATH.open("rb") as source:
        sample_bytes = source.read(128_000)

    for encoding in ("utf-8-sig", "cp1252", "latin-1"):
        try:
            sample_text = sample_bytes.decode(encoding)
            break
        except UnicodeDecodeError:
            continue
    else:
        raise ValueError("Could not decode the CSV sample.")

    try:
        delimiter = csv.Sniffer().sniff(
            sample_text,
            delimiters=",;\t|",
        ).delimiter
    except csv.Error:
        delimiter = ","

    return encoding, delimiter


def main() -> None:
    if not INPUT_PATH.exists():
        raise FileNotFoundError(
            f"Dataset not found: {INPUT_PATH}\n"
            "Run python scripts/download_data.py first."
        )

    encoding, delimiter = detect_format()

    read_options = {
        "encoding": encoding,
        "sep": delimiter,
        "dtype": "string",
        "keep_default_na": False,
    }

    sample = pd.read_csv(INPUT_PATH, nrows=5, **read_options)
    columns = sample.columns.tolist()

    category_columns = [
        column for column in columns
        if column.upper() in CATEGORY_CANDIDATES
    ]

    date_columns = [
        column for column in columns
        if "DATE" in column.upper()
    ]

    missing_counts = pd.Series(0, index=columns, dtype="int64")
    category_counts = {
        column: Counter() for column in category_columns
    }

    total_rows = 0

    print("Inspecting the dataset in chunks...")

    for chunk_number, chunk in enumerate(
        pd.read_csv(INPUT_PATH, chunksize=CHUNK_SIZE, **read_options),
        start=1,
    ):
        total_rows += len(chunk)

        # Count empty or whitespace-only cells as missing.
        stripped = chunk.apply(lambda column: column.str.strip())
        missing_counts += stripped.eq("").sum()

        for column in category_columns:
            values = stripped[column]
            values = values[values.ne("")]
            category_counts[column].update(
                values.value_counts().to_dict()
            )

        if chunk_number % 10 == 0:
            print(f"Inspected {total_rows:,} rows")

    lines = []

    def add(text: str = "") -> None:
        lines.append(text)

    add("MONTRÉAL 311 DATA INSPECTION")
    add()
    add("1. FILE AND DATASET SIZE")
    add(f"File: {INPUT_PATH.name}")
    add(f"Encoding: {encoding}")
    add(f"Delimiter: {delimiter!r}")
    add(f"Rows: {total_rows:,}")
    add(f"Columns: {len(columns)}")

    add()
    add("2. COLUMN NAMES")
    for column in columns:
        add(column)

    add()
    add("3. FIRST FIVE ROWS")
    add(sample.to_string(index=False))

    add()
    add("4. MISSING VALUES")
    missing_table = missing_counts.rename("missing_count").to_frame()
    if total_rows:
        missing_table["missing_pct"] = (
            missing_table["missing_count"] / total_rows * 100
        ).round(2)
    add(missing_table.to_string())

    add()
    add("5. COMMON CATEGORY VALUES")
    if not category_columns:
        add("No predefined category columns matched.")
        add("Review the column names before selecting category fields.")

    for column in category_columns:
        add()
        add(f"{column}:")
        for value, count in category_counts[column].most_common(20):
            add(f"  {value}: {count:,}")

    add()
    add("6. RAW DATE EXAMPLES — FIRST FIVE ROWS ONLY")
    if date_columns:
        add(sample[date_columns].to_string(index=False))
    else:
        add("No column name contains DATE.")

    add()
    add("7. INTERPRETATION NOTES")
    add("All fields were read as text for this initial inspection.")
    add("Date formats and identifier uniqueness are not yet validated.")
    add("Blank cells are counted as missing; other markers are preserved.")
    add("Category counts cover the entire downloaded dataset.")

    report = "\n".join(lines)
    REPORT_PATH.write_text(report + "\n", encoding="utf-8")

    print()
    print(report)
    print(f"\nSaved inspection report: {REPORT_PATH}")


if __name__ == "__main__":
    main()