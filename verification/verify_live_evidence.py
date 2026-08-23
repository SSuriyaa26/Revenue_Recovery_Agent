"""Verification script providing hard evidence for:
1. Exact contents, entry count, and transcript mapping of data/.cache_eval_extractions.json
2. Direct raw HTTP query to Razorpay API for plink_TTGwFzhJGC5eFC and plink_TTGwL5ErAWdjGJ + listing recent payment links
"""

import json
import os
import sys
from pathlib import Path
import requests
from dotenv import load_dotenv

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

load_dotenv()

print("=" * 80)
print("CHECK 1: EXACT CACHE CONTENTS & ENTRY COUNT (data/.cache_eval_extractions.json)")
print("=" * 80)

cache_path = Path("data/.cache_eval_extractions.json")
if not cache_path.exists():
    print("CACHE FILE DOES NOT EXIST!")
else:
    with open(cache_path, "r", encoding="utf-8") as f:
        cache_data = json.load(f)

    print(f"Total Cached Entries: {len(cache_data)}")
    print(f"Cache File Size: {cache_path.stat().st_size} bytes\n")
    print("Listing all cached entries with extracted values:")
    print("-" * 80)
    for idx, (k, v) in enumerate(cache_data.items(), 1):
        data = v.get("data", {})
        model = v.get("model", "")
        amt = data.get("committed_amount")
        dt = data.get("committed_date")
        conf = data.get("confidence")
        notes = data.get("extraction_notes", "")[:60]
        print(f"{idx:02d}. Key: {k[:12]}... | Model: {model:<18} | Amt: {str(amt):<8} | Date: {str(dt):<10} | Conf: {conf} | Notes: {notes}...")

print("\n" + "=" * 80)
print("CHECK 2: DIRECT LIVE RAZORPAY API FETCH (RAW HTTP CALLS)")
print("=" * 80)

key_id = os.getenv("RAZORPAY_KEY_ID")
key_secret = os.getenv("RAZORPAY_KEY_SECRET")
auth = (key_id, key_secret)

print(f"Using Key ID: {key_id}")
print(f"Auth configured: {'YES' if key_secret else 'NO'}\n")

# A. Fetch specific link 1
link_id_1 = "plink_TTGwFzhJGC5eFC"
url_1 = f"https://api.razorpay.com/v1/payment_links/{link_id_1}"
print(f"[A] GET {url_1}")
resp_1 = requests.get(url_1, auth=auth, timeout=15)
print(f"    HTTP Status: {resp_1.status_code}")
print(f"    Headers Server: {resp_1.headers.get('server', 'unknown')}")
print(f"    Response Body:")
try:
    print(json.dumps(resp_1.json(), indent=4))
except Exception:
    print(resp_1.text)

print("-" * 80)

# B. Fetch specific link 2
link_id_2 = "plink_TTGwL5ErAWdjGJ"
url_2 = f"https://api.razorpay.com/v1/payment_links/{link_id_2}"
print(f"[B] GET {url_2}")
resp_2 = requests.get(url_2, auth=auth, timeout=15)
print(f"    HTTP Status: {resp_2.status_code}")
print(f"    Response Body:")
try:
    print(json.dumps(resp_2.json(), indent=4))
except Exception:
    print(resp_2.text)

print("-" * 80)

# C. List all payment links on this Razorpay account
url_list = "https://api.razorpay.com/v1/payment_links?count=10"
print(f"[C] GET {url_list} (Listing latest 10 payment links on this Razorpay Merchant Account)")
resp_list = requests.get(url_list, auth=auth, timeout=15)
print(f"    HTTP Status: {resp_list.status_code}")
try:
    items = resp_list.json().get("payment_links", [])
    print(f"    Total Payment Links Returned: {len(items)}")
    for item in items:
        print(f"      - ID: {item.get('id')} | Amount: ₹{item.get('amount')/100:.2f} | Status: {item.get('status')} | Short URL: {item.get('short_url')} | Created: {item.get('created_at')}")
except Exception:
    print(resp_list.text)

print("\n" + "=" * 80)
print("EVIDENCE VERIFICATION COMPLETE")
print("=" * 80)
