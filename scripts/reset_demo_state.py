"""Demo State Reset Script — Video Demo Recording Preparation.

Resets all data store state (invoices, audit logs, scheduled jobs, idempotency keys)
back to a clean, known starting point. Ensures every video recording take starts from
an identical, pristine state with zero leftover state from previous runs.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

# Ensure UTF-8 on Windows terminal
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from store import (
    _audit_log,
    _idempotency_keys,
    _invoices,
    _messages_sent,
    _payment_events,
    _scheduled_jobs,
    get_audit_log,
    get_invoice,
    reset_store,
    set_invoice_status,
    update_invoice,
)

DATA_DIR = PROJECT_ROOT / "data"
CHECKSUMS_FILE = DATA_DIR / "checksums.json"


def verify_dataset_checksums() -> bool:
    """Verify that all frozen evaluation datasets are intact with valid SHA-256 hashes."""
    import hashlib

    if not CHECKSUMS_FILE.exists():
        print(f"  [ERROR] Checksums manifest missing at: {CHECKSUMS_FILE}")
        return False

    with open(CHECKSUMS_FILE, "r", encoding="utf-8") as f:
        manifest = json.load(f)

    files_dict = manifest.get("files", {})
    all_ok = True

    for filename, info in files_dict.items():
        expected_sha = info.get("checksum", "")
        filepath = DATA_DIR / filename
        if not filepath.exists():
            print(f"  [ERROR] Dataset file missing: {filename}")
            all_ok = False
            continue

        with open(filepath, "r", encoding="utf-8") as f:
            content = f.read()

        actual_sha = hashlib.sha256(content.encode("utf-8")).hexdigest()
        if actual_sha != expected_sha:
            print(f"  [ERROR] Checksum mismatch on {filename}! Expected: {expected_sha[:16]}..., Actual: {actual_sha[:16]}...")
            all_ok = False

    return all_ok


def seed_demo_invoices() -> None:
    """Seed clean, known demo baseline invoices for scripted video recording."""
    # 1. Golden Path Voice / P2P Interaction
    set_invoice_status("INV-DEMO-001", "Open")
    update_invoice(
        "INV-DEMO-001",
        customer_name="Acme Corp (Ramesh Sharma)",
        customer_phone="+919876543210",
        customer_email="ramesh@acmecorp.in",
        original_amount=100000.0,
        due_date="2026-08-15",
    )

    # 2. Guardrail Denial / Over-Cap Discount Interaction
    set_invoice_status("INV-OVERCAP-001", "Open")
    update_invoice(
        "INV-OVERCAP-001",
        customer_name="Metro Retailers (Anil Verma)",
        customer_phone="+919811223344",
        customer_email="anil@metroretail.com",
        original_amount=100000.0,
        due_date="2026-08-10",
    )

    # 3. Race-Condition Scenario (Invoice already Paid before follow-up triggers)
    set_invoice_status("INV-RACE-001", "Paid")
    update_invoice(
        "INV-RACE-001",
        customer_name="Zenith Enterprises (Pooja Patel)",
        customer_phone="+919822334455",
        original_amount=50000.0,
        due_date="2026-08-01",
    )

    # 4. Duplicate Webhook Scenario
    set_invoice_status("INV-DUP-001", "Open")
    update_invoice(
        "INV-DUP-001",
        customer_name="Apex Global (Karan Gupta)",
        customer_phone="+919833445566",
        original_amount=75000.0,
        due_date="2026-08-05",
    )


def reset_demo_state() -> bool:
    """Execute complete reset of demo environment state."""
    # Step 1: Wipe all in-memory store tables
    reset_store()

    # Step 2: Seed fresh baseline demo entities
    seed_demo_invoices()

    # Step 3: Verify dataset integrity
    checksums_ok = verify_dataset_checksums()

    return checksums_ok


def main():
    print("=" * 80)
    print("  AI REVENUE RECOVERY AGENT — DEMO STATE RESET & VERIFICATION")
    print("=" * 80)
    print("Resetting all data store state to clean baseline for video recording...")

    ok = reset_demo_state()

    print("\n  [✓] In-Memory Data Store Reset:")
    print(f"      - Invoices Seeded:        {len(_invoices)} clean records (INV-DEMO-001, INV-OVERCAP-001, etc.)")
    print(f"      - Audit Log Entries:      {len(_audit_log)} (wiped)")
    print(f"      - Idempotency Keys:       {len(_idempotency_keys)} (wiped)")
    print(f"      - Scheduled Jobs:         {len(_scheduled_jobs)} (wiped)")
    print(f"      - Message Counters:       {len(_messages_sent)} (wiped)")

    if ok:
        print("\n  [✓] Dataset Checksum Verification:")
        print("      - All frozen held-out & adversarial datasets verified SHA-256 match.")
        print("\n" + "=" * 80)
        print("  DEMO STATE PRISTINE & READY FOR NEXT RECORDING TAKE")
        print("=" * 80)
        sys.exit(0)
    else:
        print("\n  [!] Checksum verification failed! Please check data/ directory.")
        sys.exit(1)


if __name__ == "__main__":
    main()
