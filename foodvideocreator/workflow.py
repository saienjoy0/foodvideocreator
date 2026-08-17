from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any

from .artifacts import get_approved, get_candidate, artifact_is_fresh
from .contract import load_contract, validate_contract
from .directives import get_directive
from .assets import latest_asset

APPROVAL_SLOT_BY_CONTROL = {"ANALYSIS_APPROVED":"ANALYSIS","SELECTION_CONFIRM_APPROVED":"SELECTION_CONFIRM","SCRIPT_DRAFT_APPROVED":"SCRIPT_DRAFT","CTA_APPROVED":"CTA_SCRIPT","SCRIPT_FINAL_APPROVED":"SCRIPT_FINAL","VIDEO_APPROVED":"VIDEO_CANDIDATE","PUBLISHING_APPROVED":"PUBLISHING","BASE_COPY_APPROVED":"BASE_COPY","BASE_IMAGES_APPROVED":"BASE_IMAGES","THUMBNAIL_BG_APPROVED":"THUMBNAIL_BG","THUMBNAIL_FINAL_APPROVED":"THUMBNAIL_TEXT"}

class WorkflowBlocked(RuntimeError): pass

class WorkflowEngine:
    def __init__(self, contract_path: str | Path): self.contract=load_contract(contract_path); validate_contract(self.contract)
    def step(self,name:str)->dict[str,Any]: return self.contract["steps"][name]
    def _control_ok(self, con: sqlite3.Connection, project_id: str, req: str) -> bool:
        if req=="RANK_SELECTION_RESOLVED": return get_directive(con,project_id,"RANK_SELECTION") is not None
        if req=="TIPS_COMPLETE": return get_candidate(con,project_id,"TIPS_SCRIPT") is not None
        if req=="ROUTE_RESOLVED": return get_directive(con,project_id,"ROUTE") in {"A","B"}
        if req=="BASE_IMAGES_APPROVED_IF_ROUTE_B": return get_directive(con,project_id,"ROUTE")!="B" or get_approved(con,project_id,"BASE_IMAGES") is not None
        slot=APPROVAL_SLOT_BY_CONTROL.get(req); return bool(slot and get_approved(con,project_id,slot) is not None)
    def ensure_data(self, con: sqlite3.Connection, project_id: str, step_name: str) -> None:
        asset_roles={"MAIN_SOURCE","EXTERNAL_RENDER","REFERENCE_VIDEO","REFERENCE_IMAGE","PRODUCT_IMAGE","VOICE_ASSET","BGM_ASSET","OTHER_ASSET"}; slot_alias={"PUBLISHING_A":"PUBLISHING","PUBLISHING_B":"PUBLISHING"}; missing=[]; stale=[]
        for dep in self.step(step_name)["data_dependencies"]:
            if dep in asset_roles:
                if latest_asset(con,project_id,dep) is None: missing.append(dep)
                continue
            slot=slot_alias.get(dep,dep); art=get_candidate(con,project_id,slot) or get_approved(con,project_id,slot,allow_pending=True)
            if not art: missing.append(dep)
            elif not artifact_is_fresh(con,art["artifact_id"]): stale.append(dep)
        if missing: raise WorkflowBlocked("DATA_DEPENDENCIES:"+",".join(missing))
        if stale: raise WorkflowBlocked("STALE_DATA_DEPENDENCIES:"+",".join(stale))
    def ensure_controls(self, con: sqlite3.Connection, project_id: str, step_name: str) -> None:
        missing=[r for r in self.step(step_name)["control_requirements"] if not self._control_ok(con,project_id,r)]
        if missing: raise WorkflowBlocked("CONTROL_REQUIREMENTS:"+",".join(missing))
    def ensure_directives(self, con: sqlite3.Connection, project_id: str, step_name: str) -> None:
        missing=[]
        for d in self.step(step_name)["required_directives"]:
            if d=="ROUTE_A": ok=get_directive(con,project_id,"ROUTE")=="A"
            elif d=="ROUTE_B": ok=get_directive(con,project_id,"ROUTE")=="B"
            else: ok=get_directive(con,project_id,d) is not None
            if not ok: missing.append(d)
        if missing: raise WorkflowBlocked("REQUIRED_DIRECTIVES:"+",".join(missing))
    def resolve_route_dependent(self, con: sqlite3.Connection, project_id: str) -> str:
        route=get_directive(con,project_id,"ROUTE")
        if route=="A": return "PUBLISHING_A"
        if route=="B": return "PUBLISHING_B"
        raise WorkflowBlocked("ROUTE_UNRESOLVED")
