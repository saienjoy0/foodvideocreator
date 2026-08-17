from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any


class AIProvider(ABC):
    @abstractmethod
    def video_semantic_analysis(self, payload: dict[str, Any]) -> dict[str, Any]: ...

    @abstractmethod
    def research_and_rank(self, payload: dict[str, Any]) -> dict[str, Any]: ...

    @abstractmethod
    def script_lab(self, payload: dict[str, Any]) -> dict[str, Any]: ...

    @abstractmethod
    def cta(self, payload: dict[str, Any]) -> dict[str, Any]: ...

    @abstractmethod
    def align_audio(self, payload: dict[str, Any]) -> dict[str, Any]: ...

    @abstractmethod
    def publishing(self, payload: dict[str, Any]) -> dict[str, Any]: ...

    @abstractmethod
    def base_copy(self, payload: dict[str, Any]) -> dict[str, Any]: ...

    @abstractmethod
    def semantic_video_qa(self, payload: dict[str, Any]) -> dict[str, Any]: ...

    @abstractmethod
    def thumbnail_copy(self, payload: dict[str, Any]) -> dict[str, Any]: ...

    @abstractmethod
    def image_semantic_qa(self, payload: dict[str, Any]) -> dict[str, Any]: ...


class VoiceProvider(ABC):
    @abstractmethod
    def synthesize(self, text: str, output_path: Path, profile: dict[str, Any]) -> dict[str, Any]: ...


class ImageProvider(ABC):
    @abstractmethod
    def reconstruct_food_background(self, source_path: Path, output_path: Path, payload: dict[str, Any]) -> dict[str, Any]: ...
