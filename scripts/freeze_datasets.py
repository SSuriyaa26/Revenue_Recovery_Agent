"""Freeze and Checksum Held-Out Datasets — EDD Step 8.

Computes SHA-256 checksums for all held-out and adversarial dataset files.
Once run, the checksums are recorded in data/checksums.json.
Any modification to a held-out file after this point invalidates all
results computed under the old checksum (EDD §3.3, §8.1).

Usage:
    python scripts/freeze_datasets.py
"""

import hashlib
import json
import os
from datetime import datetime, UTC
from pathlib import Path


def compute_file_checksum(filepath: str) -> str:
    """Compute SHA-256 checksum of a file."""
    sha256 = hashlib.sha256()
    with open(filepath, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            sha256.update(chunk)
    return sha256.hexdigest()


def validate_dataset(filepath: str, expected_count: int, dataset_type: str) -> dict:
    """Validate a dataset file and return metadata."""
    with open(filepath, "r", encoding="utf-8") as f:
        data = json.load(f)

    actual_count = len(data)
    if actual_count != expected_count:
        print(f"  [WARN]  WARNING: {filepath} has {actual_count} records, expected {expected_count}")

    return {
        "file": os.path.basename(filepath),
        "record_count": actual_count,
        "dataset_type": dataset_type,
        "checksum": compute_file_checksum(filepath),
    }


def main():
    # Resolve paths relative to project root
    project_root = Path(__file__).parent.parent
    data_dir = project_root / "data"

    print("=" * 60)
    print("  Dataset Freeze & Checksum — EDD Step 8")
    print("=" * 60)
    print()

    # Define files to checksum with expected record counts
    files_to_checksum = [
        ("p2p_held_out.json", 35, "held_out"),
        ("p2p_adversarial.json", 12, "adversarial"),
        ("p2p_dev.json", 15, "dev"),
        ("payment_failure_held_out.json", 35, "held_out"),
        ("payment_failure_adversarial.json", 12, "adversarial"),
        ("payment_failure_dev.json", 15, "dev"),
    ]

    results = {}
    all_valid = True

    for filename, expected_count, dataset_type in files_to_checksum:
        filepath = data_dir / filename
        if not filepath.exists():
            print(f"  [FAIL] MISSING: {filename}")
            all_valid = False
            continue

        info = validate_dataset(str(filepath), expected_count, dataset_type)
        results[filename] = info
        status = "[OK]" if info["record_count"] == expected_count else "[WARN]"
        print(f"  {status} {filename}")
        print(f"     Records: {info['record_count']} (expected {expected_count})")
        print(f"     SHA-256: {info['checksum']}")
        print()

    # Write checksums file
    checksums_output = {
        "frozen_at": datetime.now(UTC).isoformat(),
        "frozen_by": "freeze_datasets.py",
        "note": "Held-out files are frozen after this timestamp. Any modification invalidates results (EDD §3.3, §8.1).",
        "files": results,
    }

    checksums_path = data_dir / "checksums.json"
    with open(checksums_path, "w", encoding="utf-8") as f:
        json.dump(checksums_output, f, indent=2)

    print("=" * 60)
    if all_valid:
        print(f"  [OK] Checksums written to: {checksums_path}")
        print("  [WARN]  DO NOT modify held-out or adversarial files after this point.")
        print("     Any change requires re-running this script (EDD §8.1).")
    else:
        print("  [FAIL] Some files are missing. Fix and re-run.")
    print("=" * 60)


if __name__ == "__main__":
    main()
