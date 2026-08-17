from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from ..artifacts import get_approved, write_json_artifact
from ..checks import claim_evidence_result, record_check
from ..providers.base import AIProvider


def run_research_ranking(con, *, project_id: str, artifact_root: str | Path, provider: AIProvider, run_id: str | None = None, rule_bundle: dict[str,Any] | None = None) -> dict[str, Any]:
    analysis_art=get_approved(con,project_id,"ANALYSIS")
    if not analysis_art: raise RuntimeError("ANALYSIS_APPROVAL_REQUIRED")
    analysis=json.loads(Path(analysis_art["path"]).read_text(encoding="utf-8"))
    result=provider.research_and_rank({"dish_identity":analysis.get("dish_identity"),"analysis":analysis,"rule_bundle":rule_bundle})
    claims=result.get("claims",[]); ranking=result.get("ranking",[])
    evidence=claim_evidence_result(claims)
    claims_art=write_json_artifact(con,project_id=project_id,artifact_type="CLAIMS",data={"claims":claims},artifact_root=artifact_root,slot="CLAIMS",filename="claims.json",created_by_run_id=run_id,dependencies=[(analysis_art["artifact_id"],analysis_art["sha256"])])
    research_art=write_json_artifact(con,project_id=project_id,artifact_type="RESEARCH",data=result,artifact_root=artifact_root,slot="RESEARCH",filename="research.json",created_by_run_id=run_id,dependencies=[(analysis_art["artifact_id"],analysis_art["sha256"])])
    ranking_art=write_json_artifact(con,project_id=project_id,artifact_type="RANKING",data={"ranking":ranking},artifact_root=artifact_root,slot="RANKING",filename="ranking.json",created_by_run_id=run_id,dependencies=[(claims_art["artifact_id"],claims_art["sha256"])])
    record_check(con,project_id,"CHECK_CLAIM_EVIDENCE",artifact_id=claims_art["artifact_id"],artifact_sha256=claims_art["sha256"],measurement={"claim_count":len(claims)},result=evidence)
    return {"claims":claims_art,"research":research_art,"ranking":ranking_art,"evidence_check":evidence,"ranking_data":ranking}
