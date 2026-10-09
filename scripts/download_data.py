import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

import requests


PROJECT_ROOT = Path(__file__).resolve().parents[1]
RAW_DIR = PROJECT_ROOT / "data" / "raw"

SOURCE_URL = (
    "https://donnees.montreal.ca/dataset/"
    "5866f832-676d-4b07-be6a-e99c21eb17e4/resource/"
    "2cfa0e06-9be4-49a6-b7f1-ee9f2363a872/download/"
    "requetes311.csv"
)

OUTPUT_PATH = RAW_DIR / "requetes311.csv"
TEMP_PATH = RAW_DIR / "requetes311.csv.part"
METADATA_PATH = RAW_DIR / "download_metadata.json"


def main() -> None:
    RAW_DIR.mkdir(parents=True, exist_ok=True)

    checksum = hashlib.sha256()
    downloaded_bytes = 0
    next_progress = 25 * 1024 * 1024

    print("Downloading Montréal 311 requests...")
    print(f"Source: {SOURCE_URL}")

    try:
        with requests.get(
            SOURCE_URL,
            stream=True,
            timeout=(30, 180),
            headers={"User-Agent": "MontrealServiceIntelligence/0.1"},
        ) as response:
            response.raise_for_status()

            content_type = response.headers.get("Content-Type", "")
            if "text/html" in content_type.lower():
                raise ValueError(
                    "The server returned an HTML page instead of a CSV."
                )

            with TEMP_PATH.open("wb") as output:
                for chunk in response.iter_content(chunk_size=1024 * 1024):
                    if not chunk:
                        continue

                    if downloaded_bytes == 0:
                        beginning = chunk.lstrip().lower()
                        if beginning.startswith((b"<!doctype html", b"<html")):
                            raise ValueError(
                                "The download contains HTML instead of CSV."
                            )

                    output.write(chunk)
                    checksum.update(chunk)
                    downloaded_bytes += len(chunk)

                    if downloaded_bytes >= next_progress:
                        print(
                            f"Downloaded "
                            f"{downloaded_bytes / (1024 * 1024):,.1f} MB"
                        )
                        next_progress += 25 * 1024 * 1024

            final_url = response.url

        if downloaded_bytes == 0:
            raise ValueError("The downloaded file is empty.")

        TEMP_PATH.replace(OUTPUT_PATH)

        metadata = {
            "dataset": "Montréal 311 requests: 2022 onward",
            "source_url": SOURCE_URL,
            "final_url": final_url,
            "downloaded_at_utc": datetime.now(timezone.utc).isoformat(),
            "filename": OUTPUT_PATH.name,
            "size_bytes": downloaded_bytes,
            "sha256": checksum.hexdigest(),
        }

        METADATA_PATH.write_text(
            json.dumps(metadata, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

        print(f"\nSaved dataset: {OUTPUT_PATH}")
        print(f"Size: {downloaded_bytes / (1024 * 1024):,.1f} MB")
        print(f"Saved source information: {METADATA_PATH}")

    except Exception:
        TEMP_PATH.unlink(missing_ok=True)
        raise


if __name__ == "__main__":
    main()