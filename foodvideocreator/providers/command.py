from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any

from .base import AIProvider, VoiceProvider, ImageProvider


class CommandJSONProvider(AIProvider):
    """Provider boundary for any external AI. Command receives JSON on stdin and returns JSON on stdout."""
    def __init__(self, command: list[str]):
        self.command = command

    def _call(self, operation: str, payload: dict[str, Any]) -> dict[str, Any]:
        proc = subprocess.run(self.command, input=json.dumps({"operation": operation, "payload": payload}, ensure_ascii=False), text=True, capture_output=True, check=True)
        return json.loads(proc.stdout)

    def video_semantic_analysis(self, payload): return self._call("video_semantic_analysis", payload)
    def research_and_rank(self, payload): return self._call("research_and_rank", payload)
    def script_lab(self, payload): return self._call("script_lab", payload)
    def cta(self, payload): return self._call("cta", payload)
    def align_audio(self, payload): return self._call("align_audio", payload)
    def publishing(self, payload): return self._call("publishing", payload)
    def base_copy(self, payload): return self._call("base_copy", payload)
    def semantic_video_qa(self, payload): return self._call("semantic_video_qa", payload)
    def thumbnail_copy(self, payload): return self._call("thumbnail_copy", payload)
    def image_semantic_qa(self, payload): return self._call("image_semantic_qa", payload)


class CommandVoiceProvider(VoiceProvider):
    def __init__(self, command: list[str]): self.command = command
    def synthesize(self, text: str, output_path: Path, profile: dict[str, Any]) -> dict[str, Any]:
        proc = subprocess.run(self.command, input=json.dumps({"text": text, "output_path": str(output_path), "profile": profile}, ensure_ascii=False), text=True, capture_output=True, check=True)
        return json.loads(proc.stdout)


class CommandImageProvider(ImageProvider):
    def __init__(self, command: list[str]): self.command = command
    def reconstruct_food_background(self, source_path: Path, output_path: Path, payload: dict[str, Any]) -> dict[str, Any]:
        proc = subprocess.run(self.command, input=json.dumps({"source_path": str(source_path), "output_path": str(output_path), "payload": payload}, ensure_ascii=False), text=True, capture_output=True, check=True)
        return json.loads(proc.stdout)
