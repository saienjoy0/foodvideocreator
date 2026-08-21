#!/usr/bin/env python3
from __future__ import annotations

import base64
import json
import os
import re
import sys
import wave
from pathlib import Path
from typing import Any

DEFAULT_MODEL = "gemini-2.5-flash-preview-tts"
DEFAULT_VOICE = "Kore"
DEFAULT_STYLE = (
    "自然な日本語のYouTube Shortsナレーション。テンポはやや速め、"
    "聞き取りやすく、過剰に芝居がからず、料理の意外性が伝わる話し方。"
)


def _fail(message: str, code: int = 2) -> None:
    print(message, file=sys.stderr)
    raise SystemExit(code)


def _audio_from_response(response: Any) -> tuple[bytes, str]:
    candidates = getattr(response, "candidates", None) or []
    if not candidates:
        raise RuntimeError("Gemini TTS returned no candidates")
    content = getattr(candidates[0], "content", None)
    parts = getattr(content, "parts", None) or []
    for part in parts:
        inline = getattr(part, "inline_data", None)
        if inline is None:
            continue
        data = getattr(inline, "data", None)
        if not data:
            continue
        if isinstance(data, str):
            data = base64.b64decode(data)
        mime_type = getattr(inline, "mime_type", None) or "audio/L16;rate=24000"
        return bytes(data), str(mime_type)
    raise RuntimeError("Gemini TTS response did not contain inline audio")


def _sample_rate_from_mime(mime_type: str) -> int:
    match = re.search(r"(?:rate|sample_rate)=(\d+)", mime_type, re.IGNORECASE)
    return int(match.group(1)) if match else 24000


def _write_wav(output_path: Path, audio: bytes, mime_type: str) -> tuple[float, int]:
    output_path.parent.mkdir(parents=True, exist_ok=True)

    if audio[:4] == b"RIFF" and audio[8:12] == b"WAVE":
        output_path.write_bytes(audio)
    else:
        rate = _sample_rate_from_mime(mime_type)
        with wave.open(str(output_path), "wb") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(rate)
            wf.writeframes(audio)

    with wave.open(str(output_path), "rb") as wf:
        rate = wf.getframerate()
        frames = wf.getnframes()
        duration = frames / float(rate)
    return duration, rate


def main() -> None:
    try:
        req = json.load(sys.stdin)
    except Exception as exc:
        _fail(f"Invalid provider request JSON: {exc}")

    text = str(req.get("text") or "").strip()
    if not text:
        _fail("text is required")
    if len(text) > 24000:
        _fail("text is too long for the Gemini TTS request")

    output_path_raw = req.get("output_path")
    if not output_path_raw:
        _fail("output_path is required")
    output_path = Path(str(output_path_raw))
    if output_path.suffix.lower() != ".wav":
        _fail("Gemini voice provider currently requires a .wav output_path")

    api_key = os.environ.get("GEMINI_API_KEY", "").strip()
    if not api_key:
        _fail("GEMINI_API_KEY is not set")

    profile = req.get("profile") or {}
    if not isinstance(profile, dict):
        _fail("profile must be a JSON object")

    model = str(profile.get("model") or os.environ.get("GEMINI_TTS_MODEL") or DEFAULT_MODEL).strip()
    voice = str(profile.get("voice_name") or os.environ.get("GEMINI_TTS_VOICE") or DEFAULT_VOICE).strip()
    style = str(profile.get("style") or os.environ.get("GEMINI_TTS_STYLE") or DEFAULT_STYLE).strip()

    if not re.fullmatch(r"[A-Za-z0-9._-]{1,80}", model):
        _fail("invalid model name")
    if not re.fullmatch(r"[A-Za-z][A-Za-z0-9_-]{0,39}", voice):
        _fail("invalid voice name")

    try:
        from google import genai
        from google.genai import types
    except Exception:
        _fail("google-genai is not installed; install with: pip install -e '.[gemini]'")

    prompt = (
        f"{style}\n\n"
        "次の本文だけを、文字を足したり省いたりせず、日本語として自然に読み上げてください。\n"
        "--- 読み上げ本文 ---\n"
        f"{text}"
    )

    try:
        client = genai.Client(api_key=api_key)
        response = client.models.generate_content(
            model=model,
            contents=prompt,
            config=types.GenerateContentConfig(
                response_modalities=["AUDIO"],
                speech_config=types.SpeechConfig(
                    voice_config=types.VoiceConfig(
                        prebuilt_voice_config=types.PrebuiltVoiceConfig(voice_name=voice)
                    )
                ),
            ),
        )
        audio, mime_type = _audio_from_response(response)
        duration, sample_rate = _write_wav(output_path, audio, mime_type)
    except Exception as exc:
        _fail(f"Gemini TTS generation failed: {type(exc).__name__}: {exc}", 1)

    result = {
        "duration": round(duration, 6),
        "sample_rate": sample_rate,
        "provider": "gemini",
        "model": model,
        "voice_name": voice,
        "mime_type": mime_type,
    }
    json.dump(result, sys.stdout, ensure_ascii=False)
    sys.stdout.write("\n")


if __name__ == "__main__":
    main()
