#!/usr/bin/env python3
"""voice_batches/<name>.json の各行を、1行ずつ WAV にする。

形式:
{
  "profile": {"voice_name": "Charon", "style": "...", "model": "gemini-3.8-flash-tts"},
  "lines": [{"id": "a01", "text": "読み上げる文"}, ...]
}
出力: voice_outputs/<name>/<id>.wav と manifest.json（id → 秒）、failed.json（失敗した行）

- キーが複数あれば（環境変数 GEMINI_API_KEYS に改行区切り）、行ごとに順番に使い、
  回数制限（429）に当たったら次のキーに切り替える。
- voice_outputs/<name>/ にすでにある行は作らない（前回の続きから）。
- 10行ごとに PROGRESS_CMD（ブランチへの push）を実行して、途中経過を残す。
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path


def is_rate_limit(err: str) -> bool:
    e = err.lower()
    return "429" in e or "resource_exhausted" in e or "quota" in e or "rate" in e and "limit" in e


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

    keys = [k.strip() for k in os.environ.get("GEMINI_API_KEYS", "").splitlines() if k.strip()]
    if not keys and os.environ.get("GEMINI_API_KEY", "").strip():
        keys = [os.environ["GEMINI_API_KEY"].strip()]
    keys = list(dict.fromkeys(keys))  # 同じキーの重複を除く
    if not keys:
        raise SystemExit("no Gemini API key")
    print(f"keys: {len(keys)}", flush=True)

    man_path = out_dir / "manifest.json"
    manifest: dict[str, float] = json.loads(man_path.read_text()) if man_path.exists() else {}
    failed: dict[str, str] = {}
    progress_cmd = os.environ.get("PROGRESS_CMD")

    def save(push: bool) -> None:
        man_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        (out_dir / "failed.json").write_text(json.dumps(failed, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        if push and progress_cmd:
            subprocess.run(progress_cmd, shell=True, check=False)

    k = 0
    made = 0
    for i, line in enumerate(lines):
        lid = str(line["id"])
        if not re.fullmatch(r"[A-Za-z0-9_-]+", lid):
            failed[lid] = "invalid id"
            continue
        wav = out_dir / f"{lid}.wav"
        if lid in manifest and wav.exists():
            continue
        text = str(line.get("text") or "").strip()
        provider_req = {"text": text, "output_path": str(wav.resolve()), "profile": profile}
        err = ""
        tries_on_this_round = 0
        for attempt in range(1, 4 * len(keys) + 4):
            env = dict(os.environ, GEMINI_API_KEY=keys[k % len(keys)])
            proc = subprocess.run(
                [sys.executable, "examples/gemini_voice_command.py"],
                input=json.dumps(provider_req, ensure_ascii=False),
                text=True,
                capture_output=True,
                env=env,
                timeout=180,
            )
            if proc.returncode == 0:
                manifest[lid] = round(float(json.loads(proc.stdout)["duration"]), 3)
                print(f"ok {i + 1}/{len(lines)} {lid} {manifest[lid]:.2f}s key#{k % len(keys) + 1}", flush=True)
                made += 1
                k += 1  # 次の行は次のキー
                break
            err = (proc.stderr or "").strip()[-300:]
            if is_rate_limit(err):
                k += 1
                tries_on_this_round += 1
                if tries_on_this_round >= len(keys):  # 全部のキーが制限中なら待つ
                    tries_on_this_round = 0
                    print(f"all keys limited, wait 40s ({lid})", flush=True)
                    time.sleep(40)
                continue
            print(f"retry {lid} #{attempt}: {err}", flush=True)
            time.sleep(5)
        else:
            failed[lid] = err
            print(f"FAILED {lid}: {err}", flush=True)
        if made and made % 10 == 0:
            save(push=True)
        time.sleep(0.5)

    save(push=True)
    print(f"done: {len(manifest)} ok, {len(failed)} failed")
    if not manifest:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
