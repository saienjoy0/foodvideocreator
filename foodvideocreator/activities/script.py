from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any

from ..artifacts import get_approved, get_candidate, write_json_artifact
from ..checks import record_check, script_lab_structure_result
from ..directives import get_directive, set_directive
from ..editorial import (
    compose_display_text,
    compose_spoken_text,
    core_promise_result,
    editorial_greenlight_result,
    hook_package_result,
    segment_density_result,
)
from ..providers.base import AIProvider


def _load_json_artifact(art: dict[str, Any] | None, required_error: str) -> dict[str, Any]:
    if not art:
        raise RuntimeError(required_error)
    return json.loads(Path(art["path"]).read_text(encoding="utf-8"))


def _analysis(con, project_id: str, *, approved: bool = True) -> tuple[dict[str, Any], dict[str, Any]]:
    art=(get_approved(con,project_id,"ANALYSIS") if approved else None) or get_candidate(con,project_id,"ANALYSIS")
    return art, _load_json_artifact(art,"ANALYSIS_REQUIRED")


def _attention_segments(con, project_id: str) -> tuple[list[dict[str, Any]], set[str]]:
    _, analysis=_analysis(con,project_id)
    segments=list(analysis.get("attention_segments") or [])
    scene_ids={str(s.get("scene_id")) for s in (analysis.get("major_scenes") or []) if s.get("scene_id")}
    if not segments:
        raise RuntimeError("ATTENTION_SEGMENTS_REQUIRED")
    return segments,scene_ids


def _selected_hook(result: dict[str, Any]) -> dict[str, Any] | None:
    hook_id=str(result.get("selected_hook_id") or "")
    packages=[p for p in (result.get("hook_packages") or []) if isinstance(p,dict)]
    if hook_id:
        for p in packages:
            if str(p.get("hook_id"))==hook_id:
                return p
    selected=result.get("selected_hook")
    return selected if isinstance(selected,dict) else None


def _density_target(attention_segments: list[dict[str, Any]]) -> dict[str, Any]:
    seconds=sum(max(0.0,float(s.get("end_sec",0))-float(s.get("start_sec",0))) for s in attention_segments if s.get("mode")=="NARRATION_REQUIRED")
    return {"mode":"SEGMENT_AWARE_V1_7","narration_required_seconds":seconds,"min":math.ceil(seconds*8.0),"max":math.floor(seconds*9.0)}


def create_selection_confirm(con, *, project_id: str, ranks: list[int], artifact_root: str | Path, video_seconds: float, provider: AIProvider | None = None, editorial_override: bool=False, run_id: str | None = None, rule_bundle: dict[str,Any] | None = None) -> dict[str, Any]:
    ranking_art=get_candidate(con,project_id,"RANKING"); claims_art=get_candidate(con,project_id,"CLAIMS")
    if not ranking_art or not claims_art: raise RuntimeError("RANKING_REQUIRED")
    analysis_art,analysis=_analysis(con,project_id)
    ranking=json.loads(Path(ranking_art["path"]).read_text(encoding="utf-8"))["ranking"]
    claims=json.loads(Path(claims_art["path"]).read_text(encoding="utf-8"))["claims"]
    selected_rank_items=[r for r in ranking if int(r.get("rank",-1)) in ranks]
    ids={r.get("claim_id") for r in selected_rank_items}
    story=[c for c in claims if c.get("claim_id") in ids]
    context=[c for c in claims if c.get("claim_type")=="CONTEXT"]
    attention=list(analysis.get("attention_segments") or [])
    payload={"selected_ranks":ranks,"story_claims":story,"context_claims":context,"video_seconds":video_seconds,"density_target":_density_target(attention)}

    selected_ids={c.get("claim_id") for c in story if c.get("claim_id")}
    allowed_claim_ids={c.get("claim_id") for c in story+context if c.get("claim_id")}
    scene_ids={str(s.get("scene_id")) for s in (analysis.get("major_scenes") or []) if s.get("scene_id")}
    valid=bool(story) and selected_ids.issubset({c.get("claim_id") for c in claims})

    if provider is None:
        greenlight_raw={}
    else:
        greenlight_raw=provider.script_lab({"selection":payload,"analysis":analysis,"video_seconds":video_seconds,"phase":"greenlight","rule_bundle":rule_bundle})
    core_promise=str(greenlight_raw.get("core_promise") or "")
    core_claim_ids=list(greenlight_raw.get("core_promise_claim_ids") or [])
    greenlight_payload=greenlight_raw.get("editorial_greenlight") or {}
    core_check=core_promise_result(core_promise,core_claim_ids,allowed_claim_ids)
    green_check=editorial_greenlight_result(greenlight_payload,allowed_claim_ids|scene_ids,override=editorial_override)
    payload.update({"core_promise":core_promise,"core_promise_claim_ids":core_claim_ids,"editorial_greenlight":green_check,"editorial_override":bool(editorial_override)})

    art=write_json_artifact(con,project_id=project_id,artifact_type="SELECTION_CONFIRM",data=payload,artifact_root=artifact_root,slot="SELECTION_CONFIRM",filename="selection_confirm.json",created_by_run_id=run_id,dependencies=[(ranking_art["artifact_id"],ranking_art["sha256"]),(claims_art["artifact_id"],claims_art["sha256"]),(analysis_art["artifact_id"],analysis_art["sha256"])])
    record_check(con,project_id,"CHECK_SELECTION_ONLY_APPROVED_CLAIMS",artifact_id=art["artifact_id"],artifact_sha256=art["sha256"],measurement={"selected_ranks":ranks,"selected_claim_ids":sorted(selected_ids)},result="PASS" if valid else "FAIL")
    record_check(con,project_id,"CHECK_CORE_PROMISE",artifact_id=art["artifact_id"],artifact_sha256=art["sha256"],measurement=core_check,result=core_check["result"])
    record_check(con,project_id,"CHECK_EDITORIAL_GREENLIGHT",artifact_id=art["artifact_id"],artifact_sha256=art["sha256"],measurement=green_check,result=green_check["result"])
    set_directive(con,project_id,"RANK_SELECTION",ranks)
    if editorial_override:
        set_directive(con,project_id,"EDITORIAL_OVERRIDE",True)
    return {"artifact":art,"selection":payload,"core_promise_check":core_check,"editorial_greenlight_check":green_check}


def _approved_selection(con, project_id: str) -> dict[str, Any]:
    art=get_approved(con,project_id,"SELECTION_CONFIRM")
    if not art: raise RuntimeError("SELECTION_CONFIRM_APPROVAL_REQUIRED")
    return json.loads(Path(art["path"]).read_text(encoding="utf-8"))


def _script_fact_integrity(selection: dict[str, Any], provider_result: dict[str, Any]) -> tuple[str,dict[str,Any]]:
    allowed={c.get("claim_id") for c in selection.get("story_claims",[])+selection.get("context_claims",[]) if c.get("claim_id")}
    used=set(provider_result.get("used_claim_ids") or [])
    fact_critic=((provider_result.get("critics") or {}).get("fact") or {}).get("pass") is True
    ok=bool(used) and used.issubset(allowed) and fact_critic
    return ("PASS" if ok else "FAIL",{"allowed_claim_ids":sorted(allowed),"used_claim_ids":sorted(used),"fact_critic_pass":fact_critic})


def run_script_draft(con, *, project_id: str, artifact_root: str | Path, provider: AIProvider, video_seconds: float, density_override: bool=False, run_id: str|None=None, rule_bundle:dict[str,Any]|None=None) -> dict[str, Any]:
    selection=_approved_selection(con,project_id)
    attention,scene_ids=_attention_segments(con,project_id)
    result=provider.script_lab({"selection":selection,"attention_segments":attention,"video_seconds":video_seconds,"phase":"draft","rule_bundle":rule_bundle})
    segment_texts=list(result.get("segment_texts") or [])
    selected_hook=_selected_hook(result)
    allowed_claim_ids={c.get("claim_id") for c in selection.get("story_claims",[])+selection.get("context_claims",[]) if c.get("claim_id")}
    hook_check=hook_package_result(selected_hook,scene_ids,allowed_claim_ids)
    text=compose_display_text(attention,segment_texts,selected_hook)
    density=segment_density_result(attention,segment_texts,full_text=text,selected_hook=selected_hook,override=density_override)
    result["selected_hook"]=selected_hook
    result["selected_text"]=text
    result["segment_texts"]=segment_texts

    lab_art=write_json_artifact(con,project_id=project_id,artifact_type="SCRIPT_LAB",data=result,artifact_root=artifact_root,slot="SCRIPT_LAB",filename="script_lab.json",created_by_run_id=run_id)
    art=write_json_artifact(con,project_id=project_id,artifact_type="SCRIPT_DRAFT",data={"text":text,"display_text":text,"segment_texts":segment_texts,"selected_hook":selected_hook,"script_lab_artifact_id":lab_art["artifact_id"]},artifact_root=artifact_root,slot="SCRIPT_DRAFT",filename="script_draft.json",created_by_run_id=run_id,dependencies=[(lab_art["artifact_id"],lab_art["sha256"])])
    lab_structure=script_lab_structure_result(result,video_seconds)
    record_check(con,project_id,"CHECK_SCRIPT_LAB_STRUCTURE",artifact_id=art["artifact_id"],artifact_sha256=art["sha256"],measurement=lab_structure,result=lab_structure["result"])
    record_check(con,project_id,"CHECK_HOOK_PACKAGE",artifact_id=art["artifact_id"],artifact_sha256=art["sha256"],measurement=hook_check,result=hook_check["result"])
    record_check(con,project_id,"CHECK_SCRIPT_DENSITY_DRAFT",artifact_id=art["artifact_id"],artifact_sha256=art["sha256"],measurement=density,result=density["result"])
    fact_result,fact_measure=_script_fact_integrity(selection,result)
    record_check(con,project_id,"CHECK_FACT_INTEGRITY",artifact_id=art["artifact_id"],artifact_sha256=art["sha256"],measurement=fact_measure,result=fact_result)
    return {"artifact":art,"density":density,"script_lab":lab_art,"hook_package":hook_check}


def run_tips(con, *, project_id: str, artifact_root: str | Path, provider: AIProvider, video_seconds: float, density_override: bool=False, run_id: str|None=None, rule_bundle:dict[str,Any]|None=None) -> dict[str, Any]:
    draft=get_approved(con,project_id,"SCRIPT_DRAFT")
    if not draft: raise RuntimeError("SCRIPT_DRAFT_APPROVAL_REQUIRED")
    draft_data=json.loads(Path(draft["path"]).read_text(encoding="utf-8"))
    selection=_approved_selection(con,project_id)
    attention,_=_attention_segments(con,project_id)
    result=provider.script_lab({"selection":selection,"attention_segments":attention,"segment_texts":draft_data.get("segment_texts") or [],"selected_hook":draft_data.get("selected_hook"),"video_seconds":video_seconds,"phase":"tips","draft_text":draft_data["text"],"rule_bundle":rule_bundle})
    segment_texts=list(result.get("segment_texts") or draft_data.get("segment_texts") or [])
    selected_hook=draft_data.get("selected_hook")
    text=compose_display_text(attention,segment_texts,selected_hook)
    density=segment_density_result(attention,segment_texts,full_text=text,selected_hook=selected_hook,override=density_override)
    art=write_json_artifact(con,project_id=project_id,artifact_type="TIPS_SCRIPT",data={"text":text,"display_text":text,"segment_texts":segment_texts,"selected_hook":selected_hook},artifact_root=artifact_root,slot="TIPS_SCRIPT",filename="tips_script.json",created_by_run_id=run_id,dependencies=[(draft["artifact_id"],draft["sha256"])])
    record_check(con,project_id,"CHECK_SCRIPT_DENSITY_TIPS",artifact_id=art["artifact_id"],artifact_sha256=art["sha256"],measurement=density,result=density["result"])
    fact_result,fact_measure=_script_fact_integrity(selection,result)
    record_check(con,project_id,"CHECK_FACT_INTEGRITY",artifact_id=art["artifact_id"],artifact_sha256=art["sha256"],measurement=fact_measure,result=fact_result)
    return {"artifact":art,"density":density}


def set_route(con, project_id: str, route: str) -> None:
    route=route.upper()
    if route not in {"A","B"}: raise ValueError("ROUTE_MUST_BE_A_OR_B")
    set_directive(con,project_id,"ROUTE",route)


def run_cta(con, *, project_id: str, artifact_root: str | Path, provider:AIProvider, video_seconds:float, cta_none: bool=False, run_id: str|None=None, rule_bundle:dict[str,Any]|None=None) -> dict[str, Any]:
    tips=get_candidate(con,project_id,"TIPS_SCRIPT")
    if not tips: raise RuntimeError("TIPS_REQUIRED")
    data=json.loads(Path(tips["path"]).read_text(encoding="utf-8")); text=data["text"]
    route=get_directive(con,project_id,"ROUTE")
    if route not in {"A","B"}: raise RuntimeError("ROUTE_REQUIRED")
    attention,_=_attention_segments(con,project_id)
    result=provider.cta({"text":text,"segment_texts":data.get("segment_texts") or [],"selected_hook":data.get("selected_hook"),"attention_segments":attention,"route":route,"cta_none":cta_none,"video_seconds":video_seconds,"rule_bundle":rule_bundle})
    segment_texts=list(result.get("segment_texts") or data.get("segment_texts") or [])
    selected_hook=data.get("selected_hook")
    cta_text=compose_display_text(attention,segment_texts,selected_hook)
    policy=result.get("policy","NONE" if cta_none else "BASE" if route=="B" else "LIKE_FOLLOW")
    if route=="A" and cta_none: set_directive(con,project_id,"CTA_POLICY","NONE")
    density=segment_density_result(attention,segment_texts,full_text=cta_text,selected_hook=selected_hook,override=get_directive(con,project_id,"DENSITY_OVERRIDE",False) is True)
    art=write_json_artifact(con,project_id=project_id,artifact_type="CTA_SCRIPT",data={"text":cta_text,"display_text":cta_text,"segment_texts":segment_texts,"selected_hook":selected_hook,"route":route,"cta_policy":policy},artifact_root=artifact_root,slot="CTA_SCRIPT",filename="cta_script.json",created_by_run_id=run_id,dependencies=[(tips["artifact_id"],tips["sha256"])])
    expected_policy="NONE" if cta_none else "BASE" if route=="B" else "LIKE_FOLLOW"
    policy_ok=policy==expected_policy
    record_check(con,project_id,"CHECK_CTA_POLICY",artifact_id=art["artifact_id"],artifact_sha256=art["sha256"],measurement={"route":route,"policy":policy,"expected_policy":expected_policy,"policy_match":policy_ok,"density":density},result="PASS" if density["result"]=="PASS" and policy_ok else "FAIL")
    return {"artifact":art,"policy":policy,"density":density}


def run_script_final(con, *, project_id: str, artifact_root: str | Path, video_seconds: float, density_override: bool=False, estimated_chars_per_second: float=10.0, run_id: str|None=None, rule_bundle:dict[str,Any]|None=None) -> dict[str, Any]:
    cta=get_approved(con,project_id,"CTA_SCRIPT")
    if not cta: raise RuntimeError("CTA_APPROVAL_REQUIRED")
    data=json.loads(Path(cta["path"]).read_text(encoding="utf-8"))
    attention,_=_attention_segments(con,project_id)
    segment_texts=list(data.get("segment_texts") or [])
    selected_hook=data.get("selected_hook")
    text=compose_display_text(attention,segment_texts,selected_hook)
    density=segment_density_result(attention,segment_texts,full_text=text,selected_hook=selected_hook,override=density_override)
    pronunciation_map=get_directive(con,project_id,"PRONUNCIATION_MAP",{}) or {}
    if not isinstance(pronunciation_map,dict): raise RuntimeError("PRONUNCIATION_MAP_MUST_BE_OBJECT")
    spoken_text=compose_spoken_text(attention,segment_texts,selected_hook)
    for display,spoken in sorted(pronunciation_map.items(),key=lambda kv:len(str(kv[0])),reverse=True):
        if display and spoken is not None: spoken_text=spoken_text.replace(str(display),str(spoken))
    audio_policy=get_directive(con,project_id,"AUDIO_POLICY")
    if audio_policy=="NO_GENERATED_VOICE":
        estimated_voice=0.0; voice_check="PASS"; voice_skipped=True
    else:
        estimated_voice=len(spoken_text.replace("\n",""))/estimated_chars_per_second
        voice_check="PASS" if estimated_voice <= video_seconds else "FAIL"; voice_skipped=False
    art=write_json_artifact(con,project_id=project_id,artifact_type="SCRIPT_FINAL",data={"text":text,"display_text":text,"spoken_text":spoken_text,"segment_texts":segment_texts,"selected_hook":selected_hook,"pronunciation_map":pronunciation_map},artifact_root=artifact_root,slot="SCRIPT_FINAL",filename="script_final.json",created_by_run_id=run_id,dependencies=[(cta["artifact_id"],cta["sha256"])])
    record_check(con,project_id,"CHECK_SCRIPT_DENSITY_FINAL",artifact_id=art["artifact_id"],artifact_sha256=art["sha256"],measurement=density,result=density["result"])
    prior_fact=con.execute("SELECT result,measurement_json FROM checks WHERE project_id=? AND check_type='CHECK_FACT_INTEGRITY' ORDER BY check_id DESC LIMIT 1",(project_id,)).fetchone()
    fact_result=prior_fact[0] if prior_fact else "FAIL"
    record_check(con,project_id,"CHECK_FACT_INTEGRITY",artifact_id=art["artifact_id"],artifact_sha256=art["sha256"],measurement={"inherited_from_approved_chain":True},result=fact_result)
    lab=get_candidate(con,project_id,"SCRIPT_LAB")
    payoff="FAIL"
    if lab:
        lab_data=json.loads(Path(lab["path"]).read_text(encoding="utf-8")); payoff="PASS" if (lab_data.get("hook_payoff") or {}).get("status")=="CLOSED" else "FAIL"
    record_check(con,project_id,"CHECK_HOOK_PAYOFF",artifact_id=art["artifact_id"],artifact_sha256=art["sha256"],measurement={"script_lab_artifact_id":lab["artifact_id"] if lab else None},result=payoff)
    record_check(con,project_id,"CHECK_VOICE_PREFLIGHT",artifact_id=art["artifact_id"],artifact_sha256=art["sha256"],measurement={"estimated_voice_duration":estimated_voice,"available":video_seconds,"skipped":voice_skipped},result=voice_check)
    return {"artifact":art,"density":density,"voice_preflight":{"estimated":estimated_voice,"result":voice_check}}


def create_script_lock(con, *, project_id: str, artifact_root: str|Path, run_id: str|None=None) -> dict[str, Any]:
    script=get_approved(con,project_id,"SCRIPT_FINAL")
    if not script: raise RuntimeError("SCRIPT_FINAL_APPROVAL_REQUIRED")
    data={"approved_script_artifact_id":script["artifact_id"],"approved_script_sha256":script["sha256"]}
    return write_json_artifact(con,project_id=project_id,artifact_type="SCRIPT_LOCK",data=data,artifact_root=artifact_root,slot="SCRIPT_LOCK",filename="script_lock.json",created_by_run_id=run_id,dependencies=[(script["artifact_id"],script["sha256"])])
