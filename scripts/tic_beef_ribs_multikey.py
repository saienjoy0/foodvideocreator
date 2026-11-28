#!/usr/bin/env python3
"""TIC beef ribs 08G: safe multi-key Gemini TTS for four approved lines.

Reads one GitHub Secret that may contain several Google API keys.
Never writes, logs or uploads secret values.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import sys
import wave
from pathlib import Path

REQUEST = Path("voice_batches/tic_beef_ribs_20261122_4lines.json")
EXPECTED = [
    "真っ赤なタレの骨付き牛肉。",
    "焼いたパンに串焼きをのせる。",
    "炭火のかまどで吊るし焼き。",
    "最後は豪快に盛り付け。",
]
KEY_PATTERN = re.compile(r"AIza[A-Za-z0-9_-]{35}")

def load_keys() -> list[str]:
    # One secret can contain three comma-, newline-, or space-separated keys,
    # including JSON or three directly concatenated 39-character API keys.
    raw = os.environ.get("GEMINI_API_KEYS", "")
    raw += "\n" + os.environ.get("GEMINI_API_KEY", "")
    found = KEY_PATTERN.findall(raw)
    keys = list(dict.fromkeys(found))
    print(f"Parsed individual API keys: {len(keys)}", flush=True)
    if len(keys) < 2:
        raise RuntimeError(
            "Fewer than two individual Google API keys found in the combined "
            "GitHub Secret; will not repeat requests using an invalid combined value"
        )
    return keys

def error_kind(stderr: str) -> str:
    lower = stderr.lower()
    if "api_key_invalid" in lower or "api key not valid" in lower or "api_key expired" in lower:
        return "invalid"
    if "429" in lower or "resource_exhausted" in lower or "quota" in lower or "rate limit" in lower:
        return "quota"
    if "permission_denied" in lower or "403" in lower or "unauthenticated" in lower or "401" in lower:
        return "permission"
    if "timed out" in lower:
        return "timeout"
    return "other"

def main() -> None:
    payload = json.loads(REQUEST.read_text(encoding="utf-8"))
    lines = payload.get("lines", [])
    actual = [line.get("text") for line in lines]
    if actual != EXPECTED or [line.get("id") for line in lines] != ["a01","a02","a03","a04"]:
        raise RuntimeError("Approved 4-line subtitle text has changed")
    profile = payload["profile"]
    if profile.get("voice_name") != "Puck" or profile.get("model") != "gemini-3.8-flash-tts":
        raise RuntimeError("Approved voice profile has changed")
    keys = load_keys()
    banned: set[int] = set()
    out = Path("voice_outputs/tic_beef_ribs_20261122_4lines")
    out.mkdir(parents=True, exist_ok=True)
    manifest: dict[str, object] = {
        "sdk": "google-genai==2.25.0",
        "model": profile["model"],
        "voice_name": profile["voice_name"],
        "approved_script_sha256": hashlib.sha256("\n".join(EXPECTED).encode("utf-8")).hexdigest(),
        "lines": {},
    }
    for line in lines:
        line_id = line["id"]
        wav = out / (line_id + ".wav")
        success = False
        # Skip invalid/quota-limited keys for the remainder of this run.
        for i, key in enumerate(keys):
            if i in banned:
                continue
            env = dict(os.environ)
            env["GEMINI_API_KEY"] = key
            request = {"text": line["text"], "output_path": str(wav.resolve()), "profile": profile}
            try:
                process = subprocess.run(
                    [sys.executable, "examples/gemini_voice_command.py"],
                    input=json.dumps(request, ensure_ascii=False),
                    capture_output=True, text=True, env=env, timeout=95,
                )
                if process.returncode != 0:
                    kind = error_kind(process.stderr)
                    print(f"{line_id}: key#{i+1} failed ({kind}); skipping", flush=True)
                    if kind in ("invalid", "quota", "permission"):
                        banned.add(i)
                    continue
                result = json.loads(process.stdout)
                with wave.open(str(wav), "rb") as wf:
                    seconds = wf.getnframes() / wf.getframerate()
                if seconds <= 0 or wav.stat().st_size < 1000:
                    print(f"{line_id}: key#{i+1} output failed validation", flush=True)
                    continue
                manifest["lines"][line_id] = {
                    "text": line["text"],
                    "duration_seconds": round(seconds, 3),
                    "sample_rate": result.get("sample_rate"),
                    "wav": wav.name,
                }
                print(f"{line_id}: generated {seconds:.3f}s using key#{i+1}", flush=True)
                success = True
                break
            except subprocess.TimeoutExpired:
                print(f"{line_id}: key#{i+1} request timeout; trying next", flush=True)
            except Exception as ex:
                print(f"{line_id}: validation problem ({type(ex).__name__}); trying next", flush=True)
        if not success:
            print(f"{line_id}: all available keys failed", flush=True)
    (out / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Keys disabled during run: {len(banned)}/{len(keys)}", flush=True)
    if len(manifest["lines"]) != 4:
        raise RuntimeError(f"Only {len(manifest['lines'])}/4 approved WAV files generated")
    print("SUCCESS: 4/4 WAVs generated from original approved subtitle lines", flush=True)

if __name__ == "__main__":
    main()
