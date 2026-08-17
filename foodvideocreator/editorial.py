from __future__ import annotations

import math
import unicodedata
from typing import Any

ALLOWED_SEGMENT_MODES = {"NARRATION_REQUIRED", "VISUAL_ONLY", "ASMR_ONLY"}
ALLOWED_AUDIO_STRATEGIES = {"VOICE", "ORIGINAL", "ORIGINAL_ASMR", "SILENCE"}


def _effective_sequence(text: str) -> str:
    out: list[str] = []
    for ch in str(text or ""):
        cat = unicodedata.category(ch)
        if ch.isspace() or cat.startswith("P") or cat.startswith("Z"):
            continue
        out.append(ch)
    return "".join(out)


def effective_char_count(text: str) -> int:
    return len(_effective_sequence(text))


def ensure_scene_ids(analysis: dict[str, Any]) -> list[str]:
    scenes = analysis.get("major_scenes") or []
    ids: list[str] = []
    for idx, scene in enumerate(scenes, start=1):
        if not isinstance(scene, dict):
            continue
        scene_id = str(scene.get("scene_id") or f"scene_{idx:02d}")
        scene["scene_id"] = scene_id
        ids.append(scene_id)
    return ids


def attention_segments_result(raw_segments: list[dict[str, Any]] | None, video_seconds: float, allowed_scene_ids: set[str]) -> dict[str, Any]:
    errors: list[str] = []
    segments = raw_segments or []
    if not segments:
        return {"result": "FAIL", "errors": ["attention_segments required"], "segment_count": 0}
    ids: set[str] = set()
    normalized: list[dict[str, Any]] = []
    for idx, raw in enumerate(segments, start=1):
        if not isinstance(raw, dict):
            errors.append(f"segment {idx} must be object")
            continue
        segment_id = str(raw.get("segment_id") or f"attn_{idx:02d}")
        try:
            start = float(raw.get("start_sec"))
            end = float(raw.get("end_sec"))
        except Exception:
            errors.append(f"segment {segment_id} has invalid window")
            continue
        mode = str(raw.get("mode") or "")
        reason = str(raw.get("reason") or "").strip()
        evidence = tuple(str(x) for x in (raw.get("evidence_scene_ids") or []) if str(x))
        if segment_id in ids:
            errors.append(f"duplicate segment_id: {segment_id}")
        ids.add(segment_id)
        if start < 0 or end <= start or end > video_seconds + 0.05:
            errors.append(f"segment {segment_id} has invalid window")
        if mode not in ALLOWED_SEGMENT_MODES:
            errors.append(f"segment {segment_id} has invalid mode")
        if not reason:
            errors.append(f"segment {segment_id} missing reason")
        if not evidence:
            errors.append(f"segment {segment_id} missing evidence_scene_ids")
        elif not set(evidence).issubset(allowed_scene_ids):
            errors.append(f"segment {segment_id} references unknown scene")
        normalized.append({"segment_id": segment_id, "start_sec": start, "end_sec": end, "mode": mode, "reason": reason, "evidence_scene_ids": list(evidence)})
    normalized.sort(key=lambda x: x["start_sec"])
    previous_end = 0.0
    for idx, seg in enumerate(normalized):
        if idx == 0 and seg["start_sec"] > 0.05:
            errors.append("attention timeline does not start at 0")
        if idx > 0:
            if seg["start_sec"] < previous_end - 0.05:
                errors.append(f"segment {seg['segment_id']} overlaps previous segment")
            elif seg["start_sec"] > previous_end + 0.05:
                errors.append(f"gap before segment {seg['segment_id']}")
        previous_end = max(previous_end, seg["end_sec"])
    if normalized and previous_end < video_seconds - 0.05:
        errors.append("attention timeline does not cover video end")
    return {"result": "PASS" if not errors else "FAIL", "errors": errors, "segment_count": len(normalized), "segments": normalized}


def core_promise_result(core_promise: str, claim_ids: list[str] | None, allowed_claim_ids: set[str]) -> dict[str, Any]:
    promise = str(core_promise or "").strip()
    ids = {str(x) for x in (claim_ids or []) if str(x)}
    errors: list[str] = []
    if not promise:
        errors.append("core_promise missing")
    if "\n" in promise:
        errors.append("core_promise must be one line")
    if not ids:
        errors.append("core_promise claim ids missing")
    elif not ids.issubset(allowed_claim_ids):
        errors.append("core_promise uses unapproved claim")
    return {"result": "PASS" if not errors else "FAIL", "errors": errors, "core_promise": promise, "claim_ids": sorted(ids)}


def editorial_greenlight_result(payload: dict[str, Any] | None, allowed_evidence_ids: set[str], *, override: bool = False) -> dict[str, Any]:
    data = payload or {}
    questions = [data.get("q1"), data.get("q2"), data.get("q3")]
    errors: list[str] = []
    no_count = 0
    for idx, q in enumerate(questions, start=1):
        if not isinstance(q, dict):
            errors.append(f"q{idx} missing")
            continue
        answer = q.get("answer")
        if answer is not True and answer is not False:
            errors.append(f"q{idx} answer must be boolean")
        elif answer is False:
            no_count += 1
        reason = str(q.get("reason") or "").strip()
        evidence = {str(x) for x in (q.get("evidence_ids") or []) if str(x)}
        if not reason:
            errors.append(f"q{idx} reason missing")
        if not evidence:
            errors.append(f"q{idx} evidence_ids missing")
        elif not evidence.issubset(allowed_evidence_ids):
            errors.append(f"q{idx} evidence outside approved inputs")
    if errors:
        decision = "INVALID"
    elif no_count == 0:
        decision = "GREENLIGHT"
    elif no_count == 1:
        decision = "REWORK"
    else:
        decision = "KILL_RECOMMEND"
    passed = not errors and (decision == "GREENLIGHT" or bool(override))
    return {"result": "PASS" if passed else "FAIL", "decision": decision, "override": bool(override), "errors": errors, "questions": questions}


def hook_package_result(package: dict[str, Any] | None, allowed_scene_ids: set[str], allowed_claim_ids: set[str]) -> dict[str, Any]:
    p = package or {}
    errors: list[str] = []
    hook_id = str(p.get("hook_id") or "").strip()
    try:
        start = float(p.get("visual_start_sec"))
        end = float(p.get("visual_end_sec"))
    except Exception:
        start = end = -1.0
        errors.append("hook visual window invalid")
    scene_ids = {str(x) for x in (p.get("visual_scene_ids") or []) if str(x)}
    claim_ids = {str(x) for x in (p.get("payoff_claim_ids") or []) if str(x)}
    subtitle = str(p.get("subtitle_text") or "")
    spoken = str(p.get("spoken_text") or "")
    audio = str(p.get("audio_strategy") or "")
    no_text = p.get("no_text") is True
    if not hook_id:
        errors.append("hook_id missing")
    if start < 0 or end <= start or end > 3.0:
        errors.append("hook must fit within 0-3 sec")
    if not scene_ids or not scene_ids.issubset(allowed_scene_ids):
        errors.append("hook visual scenes invalid")
    if not claim_ids or not claim_ids.issubset(allowed_claim_ids):
        errors.append("hook payoff claims invalid")
    if not str(p.get("promise") or "").strip():
        errors.append("hook promise missing")
    if audio not in ALLOWED_AUDIO_STRATEGIES:
        errors.append("hook audio strategy invalid")
    if no_text and (subtitle.strip() or spoken.strip()):
        errors.append("no_text hook contains text")
    if not no_text and not (subtitle.strip() or spoken.strip()):
        errors.append("text hook has no text")
    if audio == "VOICE" and not spoken.strip():
        errors.append("VOICE hook requires spoken_text")
    critics = p.get("critics") or {}
    for name in ("viewer", "shorts_editor", "fact", "procedure"):
        if ((critics.get(name) or {}).get("pass")) is not True:
            errors.append(f"selected hook {name} critic failed")
    return {"result": "PASS" if not errors else "FAIL", "errors": errors, "hook_id": hook_id}


def _hook_display_text(hook: dict[str, Any] | None) -> str:
    p = hook or {}
    if p.get("no_text") is True:
        return ""
    return str(p.get("subtitle_text") or p.get("spoken_text") or "")


def hook_spoken_text(hook: dict[str, Any] | None) -> str:
    p = hook or {}
    if p.get("no_text") is True or p.get("audio_strategy") != "VOICE":
        return ""
    return str(p.get("spoken_text") or "")


def compose_display_text(attention_segments: list[dict[str, Any]], segment_texts: list[dict[str, Any]], selected_hook: dict[str, Any] | None) -> str:
    by_id = {str(x.get("segment_id")): str(x.get("text") or "") for x in segment_texts if isinstance(x, dict)}
    parts = [_hook_display_text(selected_hook)]
    for seg in sorted(attention_segments, key=lambda x: float(x.get("start_sec", 0))):
        if str(seg.get("mode")) == "NARRATION_REQUIRED":
            parts.append(by_id.get(str(seg.get("segment_id")), ""))
    return "".join(parts)


def compose_spoken_text(attention_segments: list[dict[str, Any]], segment_texts: list[dict[str, Any]], selected_hook: dict[str, Any] | None) -> str:
    by_id = {str(x.get("segment_id")): str(x.get("text") or "") for x in segment_texts if isinstance(x, dict)}
    parts = [hook_spoken_text(selected_hook)]
    for seg in sorted(attention_segments, key=lambda x: float(x.get("start_sec", 0))):
        if str(seg.get("mode")) == "NARRATION_REQUIRED":
            parts.append(by_id.get(str(seg.get("segment_id")), ""))
    return "".join(parts)


def segment_density_result(attention_segments: list[dict[str, Any]], segment_texts: list[dict[str, Any]], *, full_text: str, selected_hook: dict[str, Any] | None = None, override: bool = False) -> dict[str, Any]:
    if not attention_segments:
        return {"result": "FAIL", "density_qa": "FAIL_ATTENTION_SEGMENTS_MISSING"}
    attn_by_id = {str(s.get("segment_id")): s for s in attention_segments}
    text_by_id: dict[str, str] = {}
    duplicate_ids: list[str] = []
    unknown_ids: list[str] = []
    for item in segment_texts or []:
        sid = str(item.get("segment_id") or "")
        if sid in text_by_id:
            duplicate_ids.append(sid)
        text_by_id[sid] = str(item.get("text") or "")
        if sid not in attn_by_id:
            unknown_ids.append(sid)
    missing_ids = sorted(set(attn_by_id) - set(text_by_id))
    narration_seconds = 0.0
    narration_chars = 0
    silent_violations: list[str] = []
    for seg in sorted(attention_segments, key=lambda x: float(x.get("start_sec", 0))):
        sid = str(seg.get("segment_id") or "")
        mode = str(seg.get("mode") or "")
        text = text_by_id.get(sid, "")
        chars = effective_char_count(text)
        if mode == "NARRATION_REQUIRED":
            narration_seconds += float(seg.get("end_sec", 0)) - float(seg.get("start_sec", 0))
            narration_chars += chars
        elif mode in {"VISUAL_ONLY", "ASMR_ONLY"} and chars:
            silent_violations.append(sid)
    low = math.ceil(narration_seconds * 8.0)
    high = math.floor(narration_seconds * 9.0)
    total_seconds = max((float(s.get("end_sec", 0)) for s in attention_segments), default=0.0)
    composed = compose_display_text(attention_segments, segment_texts, selected_hook)
    text_consistent = _effective_sequence(composed) == _effective_sequence(full_text)
    if override:
        qa = "PASS_OVERRIDE"
    elif duplicate_ids:
        qa = "FAIL_DUPLICATE_SEGMENT_TEXT"
    elif unknown_ids:
        qa = "FAIL_UNKNOWN_SEGMENT_TEXT"
    elif missing_ids:
        qa = "FAIL_MISSING_SEGMENT_TEXT"
    elif silent_violations:
        qa = "FAIL_SILENT_SEGMENT_HAS_TEXT"
    elif not text_consistent:
        qa = "FAIL_TEXT_SEGMENT_MISMATCH"
    elif narration_chars < low:
        qa = "FAIL_LOW"
    elif narration_chars > high:
        qa = "FAIL_HIGH"
    else:
        qa = "PASS"
    return {
        "result": "PASS" if qa in {"PASS", "PASS_OVERRIDE"} else "FAIL",
        "density_qa": qa,
        "narration_required_seconds": narration_seconds,
        "effective_chars": narration_chars,
        "chars_per_narrated_sec": narration_chars / narration_seconds if narration_seconds else 0.0,
        "speech_occupancy": narration_seconds / total_seconds if total_seconds else 0.0,
        "density_min": low,
        "density_max": high,
        "silent_segment_violations": silent_violations,
        "missing_segment_text_ids": missing_ids,
        "unknown_segment_text_ids": unknown_ids,
        "duplicate_segment_text_ids": duplicate_ids,
        "text_consistent": text_consistent,
        "hook_effective_chars_excluded": effective_char_count(_hook_display_text(selected_hook)),
        "mode": "SEGMENT_AWARE_V1_7",
    }
