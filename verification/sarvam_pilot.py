import os
import sys
import json
from pathlib import Path
import requests
from dotenv import load_dotenv

# Ensure UTF-8 output in Windows console
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

load_dotenv()

SARVAM_API_KEY = os.getenv("SARVAM_API_KEY")
if not SARVAM_API_KEY:
    print("ERROR: SARVAM_API_KEY not found in environment / .env", file=sys.stderr)
    sys.exit(1)

SPEECH_DIR = Path("Speech_test")
ORIGINAL_TEXT_FILE = SPEECH_DIR / "Original Text.txt"

if not ORIGINAL_TEXT_FILE.exists():
    print(f"ERROR: {ORIGINAL_TEXT_FILE} not found", file=sys.stderr)
    sys.exit(1)

with open(ORIGINAL_TEXT_FILE, "r", encoding="utf-8") as f:
    original_lines = [line.strip() for line in f.readlines() if line.strip()]

print(f"Loaded {len(original_lines)} reference phrases from {ORIGINAL_TEXT_FILE}\n")

ENDPOINT = "https://api.sarvam.ai/speech-to-text"
HEADERS = {
    "api-subscription-key": SARVAM_API_KEY
}

results = []

for i in range(1, 9):
    filename = f"Phrase {i}.m4a"
    audio_path = SPEECH_DIR / filename
    if not audio_path.exists():
        print(f"Warning: {audio_path} does not exist, skipping.")
        continue
    
    orig_text = original_lines[i-1] if i-1 < len(original_lines) else "N/A"
    
    print(f"--> Transcribing {filename} via Sarvam Saaras v3 (mode=codemix)...")
    
    with open(audio_path, "rb") as audio_file:
        files = {
            "file": (filename, audio_file, "audio/mp4")
        }
        data = {
            "model": "saaras:v3",
            "mode": "codemix"
        }
        try:
            resp = requests.post(ENDPOINT, headers=HEADERS, files=files, data=data, timeout=30)
            if resp.status_code == 200:
                resp_json = resp.json()
                transcript = resp_json.get("transcript", "")
                language_code = resp_json.get("language_code", "unknown")
                confidence = resp_json.get("confidence", "N/A")
                
                results.append({
                    "phrase_num": i,
                    "filename": filename,
                    "original": orig_text,
                    "transcription": transcript,
                    "language_code": language_code,
                    "confidence": confidence,
                    "raw_response": resp_json,
                    "status": "SUCCESS"
                })
                print(f"    [OK] Transcribed: {transcript}")
            else:
                print(f"    [ERROR {resp.status_code}] {resp.text}")
                results.append({
                    "phrase_num": i,
                    "filename": filename,
                    "original": orig_text,
                    "transcription": f"ERROR {resp.status_code}: {resp.text}",
                    "language_code": "N/A",
                    "confidence": "N/A",
                    "raw_response": resp.text,
                    "status": f"FAILED_{resp.status_code}"
                })
        except Exception as e:
            print(f"    [EXCEPTION] {e}")
            results.append({
                "phrase_num": i,
                "filename": filename,
                "original": orig_text,
                "transcription": f"EXCEPTION: {str(e)}",
                "language_code": "N/A",
                "confidence": "N/A",
                "raw_response": str(e),
                "status": "EXCEPTION"
            })

# Save detailed results to scratch/
output_json = Path("scratch/sarvam_pilot_results.json")
with open(output_json, "w", encoding="utf-8") as f:
    json.dump(results, f, ensure_ascii=False, indent=2)

print("\n" + "=" * 80)
print("SARVAM AI PILOT TEST RESULTS (Saaras v3 / codemix mode)")
print("=" * 80)

for r in results:
    print(f"\n--- Phrase {r['phrase_num']} ({r['filename']}) ---")
    print(f"  Original:      {r['original']}")
    print(f"  Transcribed:   {r['transcription']}")
    print(f"  Language Code: {r['language_code']} | Confidence: {r['confidence']} | Status: {r['status']}")

print("\n" + "=" * 80)
print(f"Pilot test complete. Raw results saved to {output_json}")
