#!/usr/bin/env python3
"""voice_batches/<name>.json の各行を、1行ずつ WAV にする。

形式:
{
  "profile": {"voice_name": "Charon", "style": "...", "model": "gemini-3.8-flash-tts"},
  "lines": [{"id": "a01", "text": "読み上げる文"}, ...]
}
出力: voice_outputs/<name>/<id>.wav と manifest.json（id → 秒）、failed.json（失敗した行）
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
import time
from pathlib import Path


def main() -> None:
    req_path = Path(sys.argv[1])
    if req_path.parent.as_posix() != "voice_batches" or req_path.suffix != ".json":
        raise SystemExit("request must be voice_batches/<name>.json")
    stem = req_path.stem
    if not re.fullmatch(r"[A-Za-z0-9_-]+", stem):
        raise SystemExit("invalid request filename")
    req = json.loads(req_path.read_text(encoding="utf-8"))
    profile = req.get("profile") or {}
    lines = req.get("lines") or []
    out_dir = Path("voice_outputs") / stem
    out_dir.mkdir(parents=True, exist_ok=True)

    manifest: dict[str, float] = {}
    failed: dict[str, str] = {}
    for i, line in enumerate(lines):
        lid = str(line["id"])
        if not re.fullmatch(r"[A-Za-z0-9_-]+", lid):
            failed[lid] = "invalid id"
            continue
        text = str(line.get("text") or "").strip()
        wav = out_dir / f"{lid}.wav"
        provider_req = {"text": text, "output_path": str(wav.resolve()), "profile": profile}
        for attempt in range(1, 7):
            proc = subprocess.run(
                [sys.executable, "examples/gemini_voice_command.py"],
                input=json.dumps(provider_req, ensure_ascii=False),
                text=True,
                capture_output=True,
            )
            if proc.returncode == 0:
                res = json.loads(proc.stdout)
                manifest[lid] = round(float(res["duration"]), 3)
                print(f"ok {i + 1}/{len(lines)} {lid} {manifest[lid]:.2f}s", flush=True)
                break
            err = (proc.stderr or "").strip()[-300:]
            wait = 30 * attempt if ("429" in err or "RESOURCE_EXHAUSTED" in err or "quota" in err.lower()) else 5 * attempt
            print(f"retry {lid} #{attempt} in {wait}s: {err}", flush=True)
            time.sleep(wait)
        else:
            failed[lid] = err
            print(f"FAILED {lid}: {err}", flush=True)
        time.sleep(1)

    (out_dir / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (out_dir / "failed.json").write_text(json.dumps(failed, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"done: {len(manifest)} ok, {len(failed)} failed")
    if not manifest:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
