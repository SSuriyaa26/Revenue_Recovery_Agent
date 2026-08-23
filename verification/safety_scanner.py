"""Step 5 Final Safety Scanner:
Checks all git-tracked files against:
1. .env presence
2. Live API keys or secrets (regex matching sk-, rzp_, gsk_, api_key =, etc.)
3. Raw audio files (*.m4a, *.wav, *.mp3)
4. Cache directories (__pycache__, .pytest_cache, venv)
5. Scratch directory files
"""

import os
import re
import subprocess
import sys

# Ensure UTF-8 output
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

# 1. Get all tracked files
res = subprocess.run(["git", "ls-files"], capture_output=True, text=True, check=True)
tracked_files = [f.strip() for f in res.stdout.strip().splitlines() if f.strip()]

print("=" * 80)
print(f"STEP 5: FINAL SAFETY AUDIT ({len(tracked_files)} TRACKED FILES)")
print("=" * 80)

# Check A: .env check
env_files = [f for f in tracked_files if ".env" in f]
print(f"[1] .env Check: {'PASSED (0 files)' if not env_files else f'FAILED: {env_files}'}")

# Check B: Raw audio check
audio_files = [f for f in tracked_files if f.lower().endswith(('.m4a', '.mp4a', '.wav', '.mp3'))]
print(f"[2] Raw Audio Files Check: {'PASSED (0 files)' if not audio_files else f'FAILED: {audio_files}'}")

# Check C: Cache & Venv check
cache_files = [f for f in tracked_files if any(p in f for p in ['__pycache__', '.pytest_cache', 'venv/', '.venv/'])]
print(f"[3] Cache & Venv Dirs Check: {'PASSED (0 files)' if not cache_files else f'FAILED: {cache_files}'}")

# Check D: Scratch directory check
scratch_files = [f for f in tracked_files if f.startswith('scratch/')]
print(f"[4] Scratch Directory Check: {'PASSED (0 files)' if not scratch_files else f'FAILED: {scratch_files}'}")

# Check E: Secret Scanner across all tracked file contents
print("[5] Secret & API Key Regex Scan across all tracked files:")
secret_patterns = [
    re.compile(r'sk-[a-zA-Z0-9_-]{20,}'),
    re.compile(r'sk_3r[a-zA-Z0-9_-]{20,}'),
    re.compile(r'gsk_[a-zA-Z0-9_-]{20,}'),
    re.compile(r'rzp_(?:test|live)_[a-zA-Z0-9]{14}'),
    re.compile(r'(?i)api[_-]?key\s*=\s*["\'][a-zA-Z0-9_-]{20,}["\']'),
]

leaks_found = []
for fpath in tracked_files:
    if fpath == "scripts/secret_scanner.py":
        continue
    try:
        with open(fpath, "r", encoding="utf-8", errors="ignore") as f:
            for line_no, line in enumerate(f, 1):
                for p in secret_patterns:
                    match = p.search(line)
                    if match:
                        leaks_found.append((fpath, line_no, match.group(0)))
    except Exception:
        pass

if not leaks_found:
    print("    PASSED: Zero secrets, hardcoded API keys, or live credentials found.")
else:
    print(f"    FAILED: Found {len(leaks_found)} potential leaks:")
    for fpath, line_no, leak in leaks_found:
        print(f"      - {fpath}:{line_no} -> {leak[:8]}...")

print("\n" + "=" * 80)
print("AUDIT RESULT: " + ("ALL CLEAR FOR PUSH" if not (env_files or audio_files or cache_files or scratch_files or leaks_found) else "ISSUES DETECTED"))
print("=" * 80)
