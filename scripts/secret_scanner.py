import sys
import subprocess
import re
from pathlib import Path

# Secret patterns to detect
PATTERNS = [
    ("Razorpay Live Key", r"\brzp_live_[A-Za-z0-9]{10,}"),
    ("Razorpay Test Key", r"\brzp_test_[A-Za-z0-9]{10,}"),
    ("OpenAI-style Secret Key", r"\bsk-[A-Za-z0-9]{20,}"),
    ("Google/Gemini API Key", r"\bAIza[A-Za-z0-9_-]{30,}"),
    ("AWS Access Key", r"\bAKIA[A-Z0-9]{16}"),
    ("Sarvam AI Key", r"\bsk_[a-z0-9]{8}_[A-Za-z0-9_-]{20,}"),
    ("Generic Hardcoded Credential", r"(api_key|secret|password|token)\s*[:=]\s*[\"'][A-Za-z0-9_-]{16,}[\"']"),
]

# Substrings that mark a line as safe mock/test data
ALLOWLIST_SUBSTRINGS = [
    "fake", "dummy", "placeholder", "your_api_key_here",
    "sample", "test_mode", "evt_", "rpevt_", "example", "mock"
]

# File extensions to skip
SKIP_EXTENSIONS = (
    ".png", ".jpg", ".jpeg", ".gif", ".pdf", ".lock", ".gitignore", ".zip", ".tar", ".gz"
)

def is_allowlisted(line: str) -> bool:
    line_lower = line.lower()
    for sub in ALLOWLIST_SUBSTRINGS:
        if sub in line_lower:
            return True
    return False

def scan_staged_files() -> int:
    """Scan staged git files for secrets. Return non-zero if secrets found."""
    try:
        res = subprocess.run(
            ["git", "diff", "--cached", "--name-only", "--diff-filter=ACM"],
            capture_output=True, text=True, check=True
        )
    except Exception as e:
        print(f"Error checking git diff: {e}", file=sys.stderr)
        return 0

    staged_files = [f.strip() for f in res.stdout.splitlines() if f.strip()]
    secrets_found = []

    for filepath in staged_files:
        p = Path(filepath)
        if p.suffix.lower() in SKIP_EXTENSIONS or p.name == ".gitignore" or "pre-commit" in p.name or "secret_scanner.py" in p.name:
            continue

        # Get STAGED content via git show :filepath
        try:
            content_res = subprocess.run(
                ["git", "show", f":{filepath}"],
                capture_output=True, text=True, check=True, errors="replace"
            )
            content = content_res.stdout
        except Exception:
            continue

        for line_num, line in enumerate(content.splitlines(), 1):
            if is_allowlisted(line):
                continue

            for name, pattern in PATTERNS:
                if re.search(pattern, line):
                    # Redact part of the line snippet for safe printing
                    snippet = line.strip()
                    if len(snippet) > 50:
                        snippet = snippet[:47] + "..."
                    secrets_found.append((filepath, line_num, name, snippet))
                    break

    if secrets_found:
        print("\n" + "=" * 65)
        print("  [COMMIT BLOCKED] POTENTIAL SECRET CREDENTIAL DETECTED!")
        print("=" * 65)
        for filepath, line_num, name, snippet in secrets_found:
            print(f"  File:   {filepath}")
            print(f"  Line:   {line_num}")
            print(f"  Type:   {name}")
            print(f"  Snippet: {snippet}")
            print("-" * 65)
        print("Please remove real credentials before committing.\n")
        return 1

    return 0

import os


def scan_all_repo_files() -> int:
    """Scan all tracked and relevant repo files for secrets quickly using pruned directory walk."""
    repo_root = Path(__file__).resolve().parent.parent
    secrets_found = []

    ignore_dirs = {".git", ".pytest_cache", "venv", ".venv", "__pycache__", "node_modules", "Speech_test", "TEST_UI", "scratch"}
    ignore_files = {".gitignore", "secret_scanner.py", ".env"}

    for root, dirs, files in os.walk(repo_root):
        # Prune ignored directories in-place so os.walk does not descend into them
        dirs[:] = [d for d in dirs if d not in ignore_dirs]

        for file_name in files:
            if file_name in ignore_files or "pre-commit" in file_name:
                continue

            p = Path(root) / file_name
            if p.suffix.lower() in SKIP_EXTENSIONS:
                continue

            try:
                with open(p, "r", encoding="utf-8", errors="replace") as f:
                    content = f.read()
            except Exception:
                continue

            rel_path = p.relative_to(repo_root)
            for line_num, line in enumerate(content.splitlines(), 1):
                if is_allowlisted(line):
                    continue

                for name, pattern in PATTERNS:
                    if re.search(pattern, line):
                        snippet = line.strip()
                        if len(snippet) > 50:
                            snippet = snippet[:47] + "..."
                        secrets_found.append((str(rel_path), line_num, name, snippet))
                        break

    if secrets_found:
        print("\n" + "=" * 65)
        print("  [ALERT] POTENTIAL SECRET CREDENTIAL DETECTED IN REPO!")
        print("=" * 65)
        for filepath, line_num, name, snippet in secrets_found:
            print(f"  File:   {filepath}")
            print(f"  Line:   {line_num}")
            print(f"  Type:   {name}")
            print(f"  Snippet: {snippet}")
            print("-" * 65)
        print("Please remove real credentials before committing or publishing.\n")
        return 1

    print("Secret Scan Clean: Zero unmasked secrets found across repository.")
    return 0


if __name__ == "__main__":
    if "--all" in sys.argv or "-a" in sys.argv:
        sys.exit(scan_all_repo_files())
    sys.exit(scan_staged_files())
