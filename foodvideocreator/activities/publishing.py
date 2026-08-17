from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from ..artifacts import get_approved, get_candidate, write_json_artifact
from ..checks import record_check, publishing_format_result
from ..directives import get_directive
from ..providers.base import AIProvider


def run_publishing(con, *, project_id:str, artifact_root:str|Path, provider:AIProvider, route:str, run_id:str|None=None, rule_bundle:dict[str,Any]|None=None)->dict[str,Any]:
    route=route.upper(); script=get_approved(con,project_id,"SCRIPT_FINAL"); selection=get_approved(con,project_id,"SELECTION_CONFIRM")
    video=get_approved(con,project_id,"VIDEO_CANDIDATE")
    if not script or not selection or not video: raise RuntimeError("PUBLISHING_INPUTS_OR_VIDEO_APPROVAL_REQUIRED")
    script_data=json.loads(Path(script["path"]).read_text(encoding="utf-8")); selection_data=json.loads(Path(selection["path"]).read_text(encoding="utf-8"))
    selected_claims=list(selection_data.get("story_claims",[]))+list(selection_data.get("context_claims",[]))
    claims_data={"claims":selected_claims,"selection_artifact_id":selection["artifact_id"]}
    cta_policy=get_directive(con,project_id,"CTA_POLICY")
    result=provider.publishing({"route":route,"script":script_data,"claims":claims_data,"cta_policy":cta_policy,"rule_bundle":rule_bundle})
    if route=="B":
        desc=result.get("description","")
        if desc.count("https://pecopeco.theshop.jp/")!=1: raise RuntimeError("BASE_URL_MUST_APPEAR_ONCE")
    art=write_json_artifact(con,project_id=project_id,artifact_type=f"PUBLISHING_{route}",data=result,artifact_root=artifact_root,slot="PUBLISHING",filename=f"publishing_{route.lower()}.json",created_by_run_id=run_id,dependencies=[(script["artifact_id"],script["sha256"]),(selection["artifact_id"],selection["sha256"]),(video["artifact_id"],video["sha256"])])
    allowed_claim_ids={c.get("claim_id") for c in claims_data.get("claims",[]) if c.get("claim_id")}
    fact_check=result.get("fact_check") or {}
    used_claim_ids=set(fact_check.get("used_claim_ids") or [])
    new_fact_detected=fact_check.get("new_fact_detected")
    facts_ok=(new_fact_detected is False and used_claim_ids.issubset(allowed_claim_ids))
    record_check(con,project_id,"CHECK_NO_NEW_FACTS",artifact_id=art["artifact_id"],artifact_sha256=art["sha256"],measurement={"allowed_claim_ids":sorted(allowed_claim_ids),"used_claim_ids":sorted(used_claim_ids),"new_fact_detected":new_fact_detected},result="PASS" if facts_ok else "FAIL")
    fmt=publishing_format_result(result,route,cta_policy=cta_policy)
    record_check(con,project_id,"CHECK_PUBLISHING_FORMAT",artifact_id=art["artifact_id"],artifact_sha256=art["sha256"],measurement=fmt,result=fmt["result"])
    return {"artifact":art,"content":result,"format_qa":fmt}


def run_base_copy(con, *, project_id:str, artifact_root:str|Path, provider:AIProvider, product_info:dict[str,Any], run_id:str|None=None, rule_bundle:dict[str,Any]|None=None)->dict[str,Any]:
    pub=get_approved(con,project_id,"PUBLISHING")
    if not pub: raise RuntimeError("PUBLISHING_APPROVAL_REQUIRED")
    result=provider.base_copy({"product_name":product_info.get("product_name"),"product_info":product_info,"rule_bundle":rule_bundle})
    art=write_json_artifact(con,project_id=project_id,artifact_type="BASE_COPY",data=result,artifact_root=artifact_root,slot="BASE_COPY",filename="base_copy.json",created_by_run_id=run_id,dependencies=[(pub["artifact_id"],pub["sha256"])])
    provided=set(product_info)
    used=set(result.get("used_product_fields") or [])
    unverified=set(result.get("unverified_product_fields") or [])
    facts_ok=used.issubset(provided) and not unverified
    record_check(con,project_id,"CHECK_CONFIRMED_PRODUCT_FACTS",artifact_id=art["artifact_id"],artifact_sha256=art["sha256"],measurement={"provided_fields":sorted(provided),"used_product_fields":sorted(used),"unverified_product_fields":sorted(unverified)},result="PASS" if facts_ok else "FAIL")
    return {"artifact":art,"content":result}
