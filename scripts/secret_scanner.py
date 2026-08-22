import sys
import subprocess
import re
from pathlib import Path

# Secret patterns to detect
PATTERNS = [
    ("Razorpay Live Key", r"rzp_live_[A-Za-z0-9]{10,}"),
    ("Razorpay Test Key", r"rzp_test_[A-Za-z0-9]{10,}"),
    ("OpenAI-style Secret Key", r"sk-[A-Za-z0-9]{20,}"),
    ("Google/Gemini API Key", r"AIza[A-Za-z0-9_-]{30,}"),
    ("AWS Access Key", r"AKIA[A-Z0-9]{16}"),
    ("Sarvam AI Key", r"sarvam_[A-Za-z0-9_-]{16,}"),
    ("Generic Hardcoded Credential", r"(api_key|secret|password|token)\s*[:=]\s*[\"'][A-Za-z0-9_-]{16,}[\"']"),
]

# Substrings that mark a line as safe mock/test data
ALLOWLIST_SUBSTRINGS = [
    "fake", "dummy", "placeholder", "your_api_key_here",
    "sample", "test_mode", "evt_", "rpevt_", "example"
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

if __name__ == "__main__":
    sys.exit(scan_staged_files())
