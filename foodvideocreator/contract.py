from __future__ import annotations

import json
from pathlib import Path
import yaml

REQUIRED_STEPS = {
    "VIDEO_ANALYSIS", "RESEARCH_RANKING", "SELECTION_CONFIRM", "SCRIPT_DRAFT", "TIPS",
    "ROUTE_SELECTION", "CTA", "SCRIPT_FINAL", "PRODUCTION", "IMPORT_EXISTING_VIDEO",
    "PUBLISHING_A", "PUBLISHING_B", "BASE_COPY", "BASE_IMAGES", "THUMBNAIL_BG",
    "THUMBNAIL_TEXT", "FINAL",
}
REQUIRED_KEYS = {"step_id", "user_visible", "data_dependencies", "control_requirements", "required_directives", "outputs", "blocking_checks", "opens_gate", "next_step"}


class ContractError(ValueError):
    pass


def load_contract(path: str | Path) -> dict:
    text = Path(path).read_text(encoding="utf-8")
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return yaml.safe_load(text)


def validate_contract(contract: dict) -> None:
    steps = contract.get("steps")
    if not isinstance(steps, dict):
        raise ContractError("steps must be an object")
    missing = REQUIRED_STEPS - set(steps)
    extra = set(steps) - REQUIRED_STEPS
    if missing:
        raise ContractError(f"missing steps: {sorted(missing)}")
    if extra:
        raise ContractError(f"unknown steps: {sorted(extra)}")
    gate_names: list[str] = []
    for name, step in steps.items():
        missing_keys = REQUIRED_KEYS - set(step)
        if missing_keys:
            raise ContractError(f"{name}: missing keys {sorted(missing_keys)}")
        if step["step_id"] != name:
            raise ContractError(f"{name}: step_id mismatch")
        if not step["outputs"]:
            raise ContractError(f"{name}: outputs must not be empty")
        if step["opens_gate"]:
            gate_names.append(step["opens_gate"])
        nxt = step["next_step"]
        if nxt is not None and nxt not in steps and nxt not in {"END", "ROUTE_DEPENDENT"}:
            raise ContractError(f"{name}: unknown next_step {nxt}")
    if len(gate_names) != len(set(gate_names)):
        raise ContractError("duplicate gate name")
