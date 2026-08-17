from __future__ import annotations

import json
import math
import sqlite3
import unicodedata
from pathlib import Path
from typing import Any

from .db import emit_event


def dish_identity_result(confidence: float, identity_conflict: bool) -> str:
    return "PASS" if confidence >= 0.80 and not identity_conflict else "NEEDS_USER_CONFIRMATION"


def effective_char_count(text: str) -> int:
    count = 0
    for ch in text:
        category = unicodedata.category(ch)
        if ch.isspace() or category.startswith("P") or category.startswith("Z"):
            continue
        count += 1
    return count


def density_bounds(video_seconds: float) -> tuple[int, int]:
    return math.ceil(video_seconds * 8.0), math.floor(video_seconds * 9.0)


def density_result(text: str, video_seconds: float, override: bool = False) -> dict[str, Any]:
    n = effective_char_count(text)
    low, high = density_bounds(video_seconds)
    passed = override or low <= n <= high
    return {"effective_chars": n, "density_min": low, "density_max": high, "chars_per_sec": n / video_seconds if video_seconds else 0.0, "result": "PASS" if passed else "FAIL", "override": bool(override)}


def script_lab_structure_result(lab: dict[str, Any], video_seconds: float) -> dict[str, Any]:
    angles=lab.get("angles") or []
    hooks=lab.get("hooks") or []
    drafts=lab.get("drafts") or []
    critics=lab.get("critics") or {}
    pairwise=lab.get("pairwise_result") or {}
    beat_map=lab.get("beat_map") or []
    payoff=lab.get("hook_payoff") or {}
    rewrite_count=lab.get("rewrite_count")
    selected_text=lab.get("selected_text") or lab.get("final_text") or ""
    used_claim_ids=lab.get("used_claim_ids") or []
    critic_ok=all(((critics.get(k) or {}).get("pass") is True) for k in ("viewer","shorts_editor","fact"))
    draft_ids={d.get("id") for d in drafts if isinstance(d,dict) and d.get("id")}
    pairwise_ok=bool(pairwise.get("winner_id")) and pairwise.get("winner_id") in draft_ids
    beats_ok=bool(beat_map)
    prev=-1.0
    for beat in beat_map:
        try:
            start=float(beat.get("start_sec")); end=float(beat.get("end_sec"))
        except Exception:
            beats_ok=False; break
        if start < 0 or end <= start or end > float(video_seconds)+1e-6 or start < prev-1e-6 or not beat.get("new_information"):
            beats_ok=False; break
        prev=end
    rewrite_ok=isinstance(rewrite_count,int) and 0 <= rewrite_count <= 1
    checks={
        "angle_count":len(angles),"hook_count":len(hooks),"draft_count":len(drafts),
        "critics_pass":critic_ok,"pairwise_pass":pairwise_ok,"beat_map_pass":beats_ok,
        "rewrite_count":rewrite_count,"hook_payoff_status":payoff.get("status"),
        "selected_text_present":bool(selected_text.strip()),"used_claim_ids_count":len(used_claim_ids),
    }
    ok=(len(angles)>=3 and 6<=len(hooks)<=10 and len(drafts)>=2 and critic_ok and pairwise_ok and beats_ok
        and rewrite_ok and payoff.get("status")=="CLOSED" and bool(selected_text.strip()) and bool(used_claim_ids))
    return {**checks,"result":"PASS" if ok else "FAIL"}


def claim_evidence_result(claims: list[dict[str, Any]]) -> str:
    if not claims:
        return "FAIL"
    allowed_classes={"history","legend","folklore","general_characteristic","unverified"}
    allowed_types={"STORY","CONTEXT"}; strengths={"high","medium","low"}
    source_required={"source_id","publisher","source_title","source_type","position","evidence_summary","url","retrieved_at"}
    positions={"supports","contradicts","uncertain"}
    for c in claims:
        if not c.get("claim_id") or c.get("claim_type") not in allowed_types or not c.get("claim"):
            return "FAIL"
        if c.get("classification") not in allowed_classes or c.get("evidence_strength") not in strengths:
            return "FAIL"
        sources=c.get("sources") or []
        if c.get("classification")!="unverified" and not sources:
            return "FAIL"
        for src in sources:
            if not source_required.issubset(src): return "FAIL"
            if src.get("position") not in positions: return "FAIL"
    return "PASS"


def record_check(con: sqlite3.Connection, project_id: str, check_type: str, *, artifact_id: str | None = None, artifact_sha256: str | None = None, measurement: dict[str, Any] | None = None, result: str, blocking: bool = True, rule_version: str = "v1") -> int:
    cur = con.execute(
        """INSERT INTO checks(project_id,check_type,artifact_id,artifact_sha256,measurement_json,result,blocking,rule_version)
           VALUES(?,?,?,?,?,?,?,?)""",
        (project_id, check_type, artifact_id, artifact_sha256, json.dumps(measurement or {}, ensure_ascii=False, sort_keys=True), result, int(blocking), rule_version),
    )
    emit_event(con, project_id, "CHECK_RECORDED", {"check_type": check_type, "artifact_id": artifact_id, "result": result, "blocking": blocking})
    con.commit()
    return int(cur.lastrowid)


def latest_check_passes(con: sqlite3.Connection, project_id: str, check_type: str, artifact_id: str | None = None) -> bool:
    if artifact_id:
        row = con.execute("SELECT result FROM checks WHERE project_id=? AND check_type=? AND artifact_id=? ORDER BY check_id DESC LIMIT 1", (project_id, check_type, artifact_id)).fetchone()
    else:
        row = con.execute("SELECT result FROM checks WHERE project_id=? AND check_type=? ORDER BY check_id DESC LIMIT 1", (project_id, check_type)).fetchone()
    return row is not None and row[0] == "PASS"


def file_basic_check(path: str | Path) -> dict[str, Any]:
    p = Path(path)
    return {"exists": p.exists(), "size": p.stat().st_size if p.exists() else 0, "result": "PASS" if p.exists() and p.stat().st_size > 0 else "FAIL"}


def publishing_format_result(content: dict[str, Any], route: str, *, cta_policy: str | None=None) -> dict[str, Any]:
    import re
    title=str(content.get("title","")).strip(); desc=str(content.get("description","")).strip(); route=route.upper()
    lines=[x.strip() for x in desc.splitlines() if x.strip()]
    tag_tokens=re.findall(r"#[^\s#]+",desc)
    url="https://pecopeco.theshop.jp/"
    body_lines=[x for x in lines if not x.startswith("#") and x!=url]
    body_chars=sum(len(x) for x in body_lines)
    # Broad Unicode emoji ranges; sufficient for deterministic structural QA.
    emoji_re=re.compile(r"[\U0001F300-\U0001FAFF\u2600-\u27BF]")
    emojis=len(emoji_re.findall("".join(body_lines)))
    url_count=desc.count(url)
    title_lines=title.count("\n")+1 if title else 0
    result={
        "title_lines":title_lines,"body_lines":len(body_lines),"body_chars":body_chars,"emoji_count":emojis,
        "hashtag_count":len(tag_tokens),"has_shorts":"#Shorts" in tag_tokens,"url_count":url_count,
    }
    if route=="A":
        ok=(title_lines==1 and 3<=len(body_lines)<=5 and 90<=body_chars<=180 and 2<=emojis<=5 and 5<=len(tag_tokens)<=8 and "#Shorts" in tag_tokens and url_count==0)
        if cta_policy=="NONE": ok=ok and "フォロー" not in desc and "いいね" not in desc
    else:
        ok=(title_lines==1 and 3<=len(body_lines)<=6 and 100<=body_chars<=200 and 2<=emojis<=5 and 5<=len(tag_tokens)<=8 and "#Shorts" in tag_tokens and url_count==1)
    result["result"]="PASS" if ok else "FAIL"
    return result
