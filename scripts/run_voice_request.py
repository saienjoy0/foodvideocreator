#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from pathlib import Path


def _safe_stem(path: Path) -> str:
    stem = path.stem
    if not stem or any(ch not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_" for ch in stem):
        raise ValueError("request filename must use only letters, numbers, '-' and '_'")
    return stem


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("request_file")
    parser.add_argument("--output-root", default="voice_outputs")
    args = parser.parse_args()

    request_path = Path(args.request_file)
    if request_path.suffix.lower() != ".json" or request_path.parent.as_posix() != "voice_requests":
        raise SystemExit("request_file must be voice_requests/<name>.json")
    if not request_path.is_file():
        raise SystemExit(f"request file not found: {request_path}")

    request_bytes = request_path.read_bytes()
    request = json.loads(request_bytes.decode("utf-8"))
    text = str(request.get("text") or "").strip()
    if not text:
        raise SystemExit("request.text is required")

    profile = request.get("profile") or {}
    if not isinstance(profile, dict):
        raise SystemExit("request.profile must be an object")

    stem = _safe_stem(request_path)
    out_dir = Path(args.output_root) / stem
    out_dir.mkdir(parents=True, exist_ok=True)
    wav_path = out_dir / "voice.wav"
    meta_path = out_dir / "metadata.json"

    provider_request = {
        "text": text,
        "output_path": str(wav_path.resolve()),
        "profile": profile,
    }
    proc = subprocess.run(
        [sys.executable, "examples/gemini_voice_command.py"],
        input=json.dumps(provider_request, ensure_ascii=False),
        text=True,
        capture_output=True,
    )
    if proc.returncode != 0:
        if proc.stderr:
            print(proc.stderr.rstrip(), file=sys.stderr)
        raise SystemExit(proc.returncode)

    provider_result = json.loads(proc.stdout)
    metadata = {
        "status": "completed",
        "request_file": request_path.as_posix(),
        "request_sha256": hashlib.sha256(request_bytes).hexdigest(),
        "text_sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(),
        "output_file": wav_path.as_posix(),
        "provider_result": provider_result,
    }
    meta_path.write_text(json.dumps(metadata, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    print(json.dumps({"stem": stem, "output_dir": out_dir.as_posix(), "metadata": metadata}, ensure_ascii=False))


if __name__ == "__main__":
    main()
