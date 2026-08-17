from __future__ import annotations

from dataclasses import dataclass, field, asdict
from enum import StrEnum
from typing import Any


class AssetRole(StrEnum):
    MAIN_SOURCE = "MAIN_SOURCE"
    EXTERNAL_RENDER = "EXTERNAL_RENDER"
    REFERENCE_VIDEO = "REFERENCE_VIDEO"
    REFERENCE_IMAGE = "REFERENCE_IMAGE"
    PRODUCT_IMAGE = "PRODUCT_IMAGE"
    VOICE_ASSET = "VOICE_ASSET"
    BGM_ASSET = "BGM_ASSET"
    OTHER_ASSET = "OTHER_ASSET"


class GateDecision(StrEnum):
    APPROVE = "APPROVE"
    REQUEST_REVISION = "REQUEST_REVISION"


class CheckResult(StrEnum):
    PASS = "PASS"
    FAIL = "FAIL"
    BLOCKED = "BLOCKED"
    NEEDS_USER_CONFIRMATION = "NEEDS_USER_CONFIRMATION"


class RunStatus(StrEnum):
    READY = "READY"
    RUNNING = "RUNNING"
    COMPLETE = "COMPLETE"
    FAILED_RETRYABLE = "FAILED_RETRYABLE"
    FAILED_BLOCKED = "FAILED_BLOCKED"
    STALE_RUN = "STALE_RUN"


class ProductionMode(StrEnum):
    GENERATED_JA_VOICE = "GENERATED_JA_VOICE"
    EXISTING_JA_VOICE = "EXISTING_JA_VOICE"
    NO_GENERATED_VOICE = "NO_GENERATED_VOICE"


@dataclass(slots=True)
class ClaimSource:
    source_id: str
    publisher: str
    source_title: str
    source_type: str
    position: str
    evidence_summary: str
    url: str = ""
    retrieved_at: str = ""


@dataclass(slots=True)
class Claim:
    claim_id: str
    claim_type: str
    claim: str
    classification: str
    evidence_strength: str
    sources: list[ClaimSource] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class ArtifactRecord:
    artifact_id: str
    project_id: str
    artifact_type: str
    version: int
    path: str
    sha256: str
    created_by_run_id: str | None = None
    step_fingerprint: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class CheckRecord:
    check_type: str
    artifact_id: str | None
    artifact_sha256: str | None
    result: str
    blocking: bool = True
    rule_version: str = "v1"
    measurement: dict[str, Any] = field(default_factory=dict)
