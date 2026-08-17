from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from ..artifacts import get_approved, get_candidate, write_json_artifact
from ..checks import density_result, record_check, script_lab_structure_result
from ..directives import get_directive, set_directive
from ..providers.base import AIProvider


def create_selection_confirm(con, *, project_id: str, ranks: list[int], artifact_root: str | Path, video_seconds: float, run_id: str | None = None) -> dict[str, Any]:
    ranking_art=get_candidate(con,project_id,"RANKING"); claims_art=get_candidate(con,project_id,"CLAIMS")
    if not ranking_art or not claims_art: raise RuntimeError("RANKING_REQUIRED")
    ranking=json.loads(Path(ranking_art["path"]).read_text(encoding="utf-8"))["ranking"]
    claims=json.loads(Path(claims_art["path"]).read_text(encoding="utf-8"))["claims"]
    selected_rank_items=[r for r in ranking if int(r.get("rank",-1)) in ranks]
    ids={r.get("claim_id") for r in selected_rank_items}
    story=[c for c in claims if c.get("claim_id") in ids]
    context=[c for c in claims if c.get("claim_type")=="CONTEXT"]
    payload={"selected_ranks":ranks,"story_claims":story,"context_claims":context,"video_seconds":video_seconds,"density_target":{"min":__import__('math').ceil(video_seconds*8),"max":__import__('math').floor(video_seconds*9)}}
    art=write_json_artifact(con,project_id=project_id,artifact_type="SELECTION_CONFIRM",data=payload,artifact_root=artifact_root,slot="SELECTION_CONFIRM",filename="selection_confirm.json",created_by_run_id=run_id,dependencies=[(ranking_art["artifact_id"],ranking_art["sha256"]),(claims_art["artifact_id"],claims_art["sha256"])])
    selected_ids={c.get("claim_id") for c in story}
    valid=bool(story) and selected_ids.issubset({c.get("claim_id") for c in claims})
    record_check(con,project_id,"CHECK_SELECTION_ONLY_APPROVED_CLAIMS",artifact_id=art["artifact_id"],artifact_sha256=art["sha256"],measurement={"selected_ranks":ranks,"selected_claim_ids":sorted(selected_ids)},result="PASS" if valid else "FAIL")
    set_directive(con,project_id,"RANK_SELECTION",ranks)
    return {"artifact":art,"selection":payload}


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
    result=provider.script_lab({"selection":selection,"video_seconds":video_seconds,"phase":"draft","rule_bundle":rule_bundle})
    text=result.get("selected_text") or result.get("final_text") or ""
    density=density_result(text,video_seconds,density_override)
    lab_art=write_json_artifact(con,project_id=project_id,artifact_type="SCRIPT_LAB",data=result,artifact_root=artifact_root,slot="SCRIPT_LAB",filename="script_lab.json",created_by_run_id=run_id)
    art=write_json_artifact(con,project_id=project_id,artifact_type="SCRIPT_DRAFT",data={"text":text,"script_lab_artifact_id":lab_art["artifact_id"]},artifact_root=artifact_root,slot="SCRIPT_DRAFT",filename="script_draft.json",created_by_run_id=run_id,dependencies=[(lab_art["artifact_id"],lab_art["sha256"])])
    lab_structure=script_lab_structure_result(result,video_seconds)
    record_check(con,project_id,"CHECK_SCRIPT_LAB_STRUCTURE",artifact_id=art["artifact_id"],artifact_sha256=art["sha256"],measurement=lab_structure,result=lab_structure["result"])
    record_check(con,project_id,"CHECK_SCRIPT_DENSITY_DRAFT",artifact_id=art["artifact_id"],artifact_sha256=art["sha256"],measurement=density,result=density["result"])
    fact_result,fact_measure=_script_fact_integrity(selection,result)
    record_check(con,project_id,"CHECK_FACT_INTEGRITY",artifact_id=art["artifact_id"],artifact_sha256=art["sha256"],measurement=fact_measure,result=fact_result)
    return {"artifact":art,"density":density,"script_lab":lab_art}


def run_tips(con, *, project_id: str, artifact_root: str | Path, provider: AIProvider, video_seconds: float, density_override: bool=False, run_id: str|None=None, rule_bundle:dict[str,Any]|None=None) -> dict[str, Any]:
    draft=get_approved(con,project_id,"SCRIPT_DRAFT")
    if not draft: raise RuntimeError("SCRIPT_DRAFT_APPROVAL_REQUIRED")
    draft_data=json.loads(Path(draft["path"]).read_text(encoding="utf-8"))
    selection=_approved_selection(con,project_id)
    result=provider.script_lab({"selection":selection,"video_seconds":video_seconds,"phase":"tips","draft_text":draft_data["text"],"rule_bundle":rule_bundle})
    text=result.get("tips_text") or draft_data["text"]
    density=density_result(text,video_seconds,density_override)
    art=write_json_artifact(con,project_id=project_id,artifact_type="TIPS_SCRIPT",data={"text":text},artifact_root=artifact_root,slot="TIPS_SCRIPT",filename="tips_script.json",created_by_run_id=run_id,dependencies=[(draft["artifact_id"],draft["sha256"])])
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
    result=provider.cta({"text":text,"route":route,"cta_none":cta_none,"video_seconds":video_seconds,"rule_bundle":rule_bundle})
    cta_text=result.get("text",text); policy=result.get("policy","NONE" if cta_none else "BASE" if route=="B" else "LIKE_FOLLOW")
    if route=="A" and cta_none: set_directive(con,project_id,"CTA_POLICY","NONE")
    density=density_result(cta_text,video_seconds,get_directive(con,project_id,"DENSITY_OVERRIDE",False) is True)
    art=write_json_artifact(con,project_id=project_id,artifact_type="CTA_SCRIPT",data={"text":cta_text,"route":route,"cta_policy":policy},artifact_root=artifact_root,slot="CTA_SCRIPT",filename="cta_script.json",created_by_run_id=run_id,dependencies=[(tips["artifact_id"],tips["sha256"])])
    expected_policy="NONE" if cta_none else "BASE" if route=="B" else "LIKE_FOLLOW"
    policy_ok=policy==expected_policy
    record_check(con,project_id,"CHECK_CTA_POLICY",artifact_id=art["artifact_id"],artifact_sha256=art["sha256"],measurement={"route":route,"policy":policy,"expected_policy":expected_policy,"policy_match":policy_ok,"density":density},result="PASS" if density["result"]=="PASS" and policy_ok else "FAIL")
    return {"artifact":art,"policy":policy,"density":density}

def run_script_final(con, *, project_id: str, artifact_root: str | Path, video_seconds: float, density_override: bool=False, estimated_chars_per_second: float=10.0, run_id: str|None=None, rule_bundle:dict[str,Any]|None=None) -> dict[str, Any]:
    cta=get_approved(con,project_id,"CTA_SCRIPT")
    if not cta: raise RuntimeError("CTA_APPROVAL_REQUIRED")
    data=json.loads(Path(cta["path"]).read_text(encoding="utf-8")); text=data["text"]
    density=density_result(text,video_seconds,density_override)
    pronunciation_map=get_directive(con,project_id,"PRONUNCIATION_MAP",{}) or {}
    if not isinstance(pronunciation_map,dict): raise RuntimeError("PRONUNCIATION_MAP_MUST_BE_OBJECT")
    spoken_text=text
    for display,spoken in sorted(pronunciation_map.items(),key=lambda kv:len(str(kv[0])),reverse=True):
        if display and spoken is not None: spoken_text=spoken_text.replace(str(display),str(spoken))
    audio_policy=get_directive(con,project_id,"AUDIO_POLICY")
    if audio_policy=="NO_GENERATED_VOICE":
        estimated_voice=0.0; voice_check="PASS"; voice_skipped=True
    else:
        estimated_voice=len(spoken_text.replace("\n",""))/estimated_chars_per_second
        voice_check="PASS" if estimated_voice <= video_seconds else "FAIL"; voice_skipped=False
    art=write_json_artifact(con,project_id=project_id,artifact_type="SCRIPT_FINAL",data={"text":text,"display_text":text,"spoken_text":spoken_text,"pronunciation_map":pronunciation_map},artifact_root=artifact_root,slot="SCRIPT_FINAL",filename="script_final.json",created_by_run_id=run_id,dependencies=[(cta["artifact_id"],cta["sha256"])])
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
