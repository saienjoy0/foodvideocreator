from __future__ import annotations

import json
import sqlite3
import uuid
from pathlib import Path
from typing import Any

from .activities import (
    run_video_analysis, run_research_ranking, create_selection_confirm, run_script_draft,
    run_tips, set_route, run_cta, run_script_final, create_script_lock, run_production,
    import_existing_video, run_publishing, run_base_copy, run_base_images, run_thumbnail_bg,
    run_thumbnail_text, run_final,
)
from .artifacts import get_candidate, get_approved, get_slot
from .checks import latest_check_passes
from .contract import load_contract, validate_contract
from .db import get_state, set_state
from .directives import get_directive, set_directive
from .gates import open_gate, decide_gate
from .workflow import WorkflowEngine, WorkflowBlocked
from .rules import load_rule_bundle
from .commands import parse_command
from .assets import latest_asset
from .startup import validate_startup
from .artifacts import sha256_file

GATE_SLOT = {
    "VIDEO_ANALYSIS":"ANALYSIS", "SELECTION_CONFIRM":"SELECTION_CONFIRM", "SCRIPT_DRAFT":"SCRIPT_DRAFT",
    "CTA":"CTA_SCRIPT", "SCRIPT_FINAL":"SCRIPT_FINAL", "PRODUCTION":"VIDEO_CANDIDATE",
    "IMPORT_EXISTING_VIDEO":"VIDEO_CANDIDATE", "PUBLISHING_A":"PUBLISHING", "PUBLISHING_B":"PUBLISHING",
    "BASE_COPY":"BASE_COPY", "BASE_IMAGES":"BASE_IMAGES", "THUMBNAIL_BG":"THUMBNAIL_BG", "THUMBNAIL_TEXT":"THUMBNAIL_TEXT",
}

CHECK_SLOT_BINDINGS = {
    "CHECK_DISH_IDENTITY":"ANALYSIS", "CHECK_CLAIM_EVIDENCE":"CLAIMS", "CHECK_THUMBNAIL_COPY_FACTS":"THUMBNAIL_COPY",
    "CHECK_SOURCE_PREPROCESS":"ANALYSIS", "CHECK_SUBTITLE_TIMING":"ALIGNMENT", "CHECK_SUBTITLE_DESIGN_PREVIEW":"SCRIPT_FINAL", "CHECK_ACTUAL_VOICE_DURATION":"SCRIPT_FINAL",
}

STEP_PRIMARY_SLOT = {
    "VIDEO_ANALYSIS":"ANALYSIS", "RESEARCH_RANKING":"CLAIMS", "SELECTION_CONFIRM":"SELECTION_CONFIRM", "SCRIPT_DRAFT":"SCRIPT_DRAFT",
    "TIPS":"TIPS_SCRIPT", "ROUTE_SELECTION":"ROUTE_SELECTION", "CTA":"CTA_SCRIPT", "SCRIPT_FINAL":"SCRIPT_FINAL",
    "PRODUCTION":"VIDEO_CANDIDATE", "IMPORT_EXISTING_VIDEO":"VIDEO_CANDIDATE", "PUBLISHING_A":"PUBLISHING", "PUBLISHING_B":"PUBLISHING",
    "BASE_COPY":"BASE_COPY", "BASE_IMAGES":"BASE_IMAGES", "THUMBNAIL_BG":"THUMBNAIL_BG", "THUMBNAIL_TEXT":"THUMBNAIL_TEXT", "FINAL":"FINAL_VIDEO",
}


class PipelineApp:
    def __init__(self, *, con:sqlite3.Connection, project_id:str, artifact_root:str|Path, contract_path:str|Path, ai_provider, voice_provider, image_provider=None, rules_dir:str|Path="rules/v4", assets_dir:str|Path="assets"):
        self.con=con; self.project_id=project_id; self.artifact_root=Path(artifact_root); self.artifact_root.mkdir(parents=True,exist_ok=True)
        self.engine=WorkflowEngine(contract_path); self.ai=ai_provider; self.voice=voice_provider; self.image=image_provider; self.rules_dir=Path(rules_dir); self.assets_dir=Path(assets_dir)
        startup=validate_startup(contract_path=contract_path,rules_dir=self.rules_dir)
        if startup["result"]!="PASS": raise RuntimeError("STARTUP_VALIDATION_FAILED:"+json.dumps(startup,ensure_ascii=False,default=str))

    def _video_seconds(self) -> float:
        art=get_approved(self.con,self.project_id,"ANALYSIS") or get_candidate(self.con,self.project_id,"ANALYSIS")
        if art:
            data=json.loads(Path(art["path"]).read_text(encoding="utf-8"))
            try:return float(data["video"]["duration"])
            except Exception: pass
        from .media import ffprobe
        src=latest_asset(self.con,self.project_id,"MAIN_SOURCE")
        if src:return float(ffprobe(src["path"])["duration"])
        raise RuntimeError("VIDEO_DURATION_UNAVAILABLE")

    def _blocking_check_failures(self, step_name:str) -> list[str]:
        failures=[]; primary_slot=STEP_PRIMARY_SLOT.get(step_name)
        for check_type in self.engine.step(step_name).get("blocking_checks",[]):
            slot=CHECK_SLOT_BINDINGS.get(check_type,primary_slot)
            art=(get_candidate(self.con,self.project_id,slot) or get_approved(self.con,self.project_id,slot,allow_pending=True)) if slot else None
            if not art or not latest_check_passes(self.con,self.project_id,check_type,art["artifact_id"]): failures.append(check_type)
        return failures

    def _open_step_gate(self, step_name:str) -> dict[str,Any] | None:
        step=self.engine.step(step_name); gate_name=step.get("opens_gate")
        if not gate_name:return None
        slot=GATE_SLOT[step_name]; art=get_candidate(self.con,self.project_id,slot)
        if not art: raise RuntimeError(f"NO_CANDIDATE_FOR_GATE:{slot}")
        missing=[]
        for c in step["blocking_checks"]:
            expected_art=art; bound_slot=CHECK_SLOT_BINDINGS.get(c)
            if bound_slot: expected_art=get_candidate(self.con,self.project_id,bound_slot) or get_approved(self.con,self.project_id,bound_slot)
            if not expected_art or not latest_check_passes(self.con,self.project_id,c,expected_art["artifact_id"]): missing.append(c)
        if missing: return {"blocked_checks": missing, "gate_name": gate_name}
        gate_id=f"gate_{step_name.lower()}_{uuid.uuid4().hex[:8]}"; pres=f"presentation_{uuid.uuid4().hex[:8]}"
        open_gate(self.con,project_id=self.project_id,gate_id=gate_id,stage=gate_name,artifact_id=art["artifact_id"],presentation_id=pres)
        return {"gate_id":gate_id,"presentation_id":pres,"artifact_id":art["artifact_id"],"artifact_sha256":art["sha256"],"gate_name":gate_name}

    def execute(self, step_name:str, **kwargs:Any)->dict[str,Any]:
        if step_name=="SELECTION_CONFIRM" and "ranks" in kwargs: set_directive(self.con,self.project_id,"RANK_SELECTION",kwargs["ranks"])
        self.engine.ensure_data(self.con,self.project_id,step_name); self.engine.ensure_controls(self.con,self.project_id,step_name); self.engine.ensure_directives(self.con,self.project_id,step_name)
        set_state(self.con,self.project_id,step_name,"RUNNING"); self.con.commit()
        route=get_directive(self.con,self.project_id,"ROUTE"); rule_bundle=load_rule_bundle(self.rules_dir,step_name,route=route)
        if step_name=="VIDEO_ANALYSIS":
            main=latest_asset(self.con,self.project_id,"MAIN_SOURCE")
            if not main: raise RuntimeError("MAIN_SOURCE_REQUIRED")
            requested=Path(kwargs.get("source_path") or main["path"])
            if not requested.exists() or sha256_file(requested)!=main["sha256"]: raise RuntimeError("VIDEO_ANALYSIS_MUST_USE_MAIN_SOURCE")
            result=run_video_analysis(self.con,project_id=self.project_id,source_path=main["path"],artifact_root=self.artifact_root,provider=self.ai,dish_name=kwargs.get("dish_name"),rule_bundle=rule_bundle)
        elif step_name=="RESEARCH_RANKING": result=run_research_ranking(self.con,project_id=self.project_id,artifact_root=self.artifact_root,provider=self.ai,rule_bundle=rule_bundle)
        elif step_name=="SELECTION_CONFIRM": result=create_selection_confirm(self.con,project_id=self.project_id,ranks=kwargs["ranks"],artifact_root=self.artifact_root,video_seconds=float(kwargs.get("video_seconds",self._video_seconds())))
        elif step_name=="SCRIPT_DRAFT": result=run_script_draft(self.con,project_id=self.project_id,artifact_root=self.artifact_root,provider=self.ai,video_seconds=float(kwargs.get("video_seconds",self._video_seconds())),density_override=bool(kwargs.get("density_override",False)),rule_bundle=rule_bundle)
        elif step_name=="TIPS": result=run_tips(self.con,project_id=self.project_id,artifact_root=self.artifact_root,provider=self.ai,video_seconds=float(kwargs.get("video_seconds",self._video_seconds())),density_override=bool(kwargs.get("density_override",False)),rule_bundle=rule_bundle)
        elif step_name=="ROUTE_SELECTION":
            route=kwargs["route"].upper(); set_route(self.con,self.project_id,route); tips=get_candidate(self.con,self.project_id,"TIPS_SCRIPT")
            if tips: self.con.execute("UPDATE artifact_slots SET current_approved_id=current_candidate_id,change_pending=0 WHERE project_id=? AND slot='TIPS_SCRIPT'",(self.project_id,)); self.con.commit()
            from .artifacts import write_json_artifact
            art=write_json_artifact(self.con,project_id=self.project_id,artifact_type="ROUTE_SELECTION",data={"route":route},artifact_root=self.artifact_root,slot="ROUTE_SELECTION",filename="route.json"); result={"artifact":art,"route":route}
        elif step_name=="CTA": result=run_cta(self.con,project_id=self.project_id,artifact_root=self.artifact_root,provider=self.ai,video_seconds=float(kwargs.get("video_seconds",self._video_seconds())),cta_none=bool(kwargs.get("cta_none",False)),rule_bundle=rule_bundle)
        elif step_name=="SCRIPT_FINAL": result=run_script_final(self.con,project_id=self.project_id,artifact_root=self.artifact_root,video_seconds=float(kwargs.get("video_seconds",self._video_seconds())),density_override=bool(kwargs.get("density_override",False)),rule_bundle=rule_bundle)
        elif step_name=="PRODUCTION": result=run_production(self.con,project_id=self.project_id,artifact_root=self.artifact_root,provider=self.ai,voice_provider=self.voice,rule_bundle=rule_bundle,assets_dir=self.assets_dir)
        elif step_name=="IMPORT_EXISTING_VIDEO": result=import_existing_video(self.con,project_id=self.project_id,artifact_root=self.artifact_root,provider=self.ai,rule_bundle=rule_bundle)
        elif step_name in {"PUBLISHING_A","PUBLISHING_B"}: result=run_publishing(self.con,project_id=self.project_id,artifact_root=self.artifact_root,provider=self.ai,route=step_name[-1],rule_bundle=rule_bundle)
        elif step_name=="BASE_COPY": result=run_base_copy(self.con,project_id=self.project_id,artifact_root=self.artifact_root,provider=self.ai,product_info=kwargs.get("product_info",{}),rule_bundle=rule_bundle)
        elif step_name=="BASE_IMAGES": result=run_base_images(self.con,project_id=self.project_id,artifact_root=self.artifact_root)
        elif step_name=="THUMBNAIL_BG": result=run_thumbnail_bg(self.con,project_id=self.project_id,artifact_root=self.artifact_root,provider=self.ai,image_provider=self.image,force_mode=kwargs.get("force_mode"),rule_bundle=rule_bundle)
        elif step_name=="THUMBNAIL_TEXT": result=run_thumbnail_text(self.con,project_id=self.project_id,artifact_root=self.artifact_root,provider=self.ai,copy_lines=kwargs.get("copy_lines"),rule_bundle=rule_bundle)
        elif step_name=="FINAL": result=run_final(self.con,project_id=self.project_id,artifact_root=self.artifact_root,rule_bundle=rule_bundle)
        else: raise KeyError(step_name)
        if self.engine.step(step_name).get("opens_gate"):
            gate=self._open_step_gate(step_name)
            if gate and gate.get("blocked_checks"): set_state(self.con,self.project_id,step_name,"BLOCKED")
            else: set_state(self.con,self.project_id,step_name,"WAITING_USER" if gate else "COMPLETE")
            self.con.commit(); return {"step":step_name,"result":result,"gate":gate,"next_step":self.engine.step(step_name)["next_step"] if not (gate and gate.get("blocked_checks")) else None}
        blocked_checks=self._blocking_check_failures(step_name)
        if blocked_checks:
            set_state(self.con,self.project_id,step_name,"BLOCKED"); self.con.commit(); return {"step":step_name,"result":result,"gate":None,"blocked_checks":blocked_checks,"next_step":None}
        set_state(self.con,self.project_id,step_name,"COMPLETE"); self.con.commit(); return {"step":step_name,"result":result,"gate":None,"next_step":self.engine.step(step_name)["next_step"]}

    def approve_open_gate(self, *, decision:str="APPROVE") -> dict[str,Any]:
        row=self.con.execute("SELECT * FROM gates WHERE project_id=? AND status='OPEN'",(self.project_id,)).fetchone()
        if not row: raise RuntimeError("NO_OPEN_GATE")
        decide_gate(self.con,project_id=self.project_id,gate_id=row["gate_id"],presentation_id=row["presentation_id"],artifact_sha256=row["artifact_sha256"],decision=decision)
        side_effect=None
        if decision=="APPROVE" and row["stage"]=="SCRIPT_FINAL_APPROVAL":
            lock=create_script_lock(self.con,project_id=self.project_id,artifact_root=self.artifact_root)
            self.con.execute("UPDATE artifact_slots SET current_approved_id=current_candidate_id,change_pending=0 WHERE project_id=? AND slot='SCRIPT_LOCK'",(self.project_id,)); self.con.commit(); side_effect=lock
        return {"gate_id":row["gate_id"],"stage":row["stage"],"decision":decision,"side_effect":side_effect}

    def confirm_dish_identity(self, dish_name:str) -> dict[str,Any]:
        from .artifacts import write_json_artifact
        from .checks import record_check
        old=get_candidate(self.con,self.project_id,"ANALYSIS")
        if not old: raise RuntimeError("ANALYSIS_CANDIDATE_REQUIRED")
        data=json.loads(Path(old["path"]).read_text(encoding="utf-8")); data["dish_identity"]=dish_name; data["dish_identity_confidence"]=1.0; data["identity_conflict"]=False
        basis=list(data.get("identity_basis",[])); basis.append("user_confirmation"); data["identity_basis"]=basis
        art=write_json_artifact(self.con,project_id=self.project_id,artifact_type="ANALYSIS",data=data,artifact_root=self.artifact_root,slot="ANALYSIS",filename="analysis.json",dependencies=[(old["artifact_id"],old["sha256"])])
        record_check(self.con,self.project_id,"CHECK_DISH_IDENTITY",artifact_id=art["artifact_id"],artifact_sha256=art["sha256"],measurement={"confidence":1.0,"identity_conflict":False,"user_confirmed":True},result="PASS")
        prev=self.con.execute("SELECT result,measurement_json FROM checks WHERE project_id=? AND check_type='CHECK_VIDEO_ANALYSIS_COMPLETE' AND artifact_id=? ORDER BY check_id DESC LIMIT 1",(self.project_id,old["artifact_id"])).fetchone()
        if prev: record_check(self.con,self.project_id,"CHECK_VIDEO_ANALYSIS_COMPLETE",artifact_id=art["artifact_id"],artifact_sha256=art["sha256"],measurement=json.loads(prev["measurement_json"]),result=prev["result"])
        gate=self._open_step_gate("VIDEO_ANALYSIS"); return {"artifact":art,"gate":gate}

    def _resolve_audio_policy_if_possible(self) -> str | None:
        existing=get_directive(self.con,self.project_id,"AUDIO_POLICY")
        if existing is not None: return existing
        analysis=get_approved(self.con,self.project_id,"ANALYSIS") or get_candidate(self.con,self.project_id,"ANALYSIS")
        if not analysis: return None
        data=json.loads(Path(analysis["path"]).read_text(encoding="utf-8")); audio=data.get("audio",{}); speech=audio.get("human_speech_present"); language=(audio.get("language") or "").lower()
        if speech is False: set_directive(self.con,self.project_id,"AUDIO_POLICY","NO_GENERATED_VOICE"); return "NO_GENERATED_VOICE"
        if speech is True and language in {"ja","jp","japanese","日本語"}:
            set_directive(self.con,self.project_id,"AUDIO_POLICY","KEEP_ORIGINAL"); set_directive(self.con,self.project_id,"EXISTING_JA_VOICE",True); return "KEEP_ORIGINAL"
        return None

    def _step_for_gate_stage(self, stage:str) -> str:
        for name,step in self.engine.contract["steps"].items():
            if step.get("opens_gate")==stage: return name
        raise RuntimeError(f"UNKNOWN_GATE_STAGE:{stage}")

    def _execute_next_after(self, step_name:str, **kwargs:Any) -> dict[str,Any]:
        next_step=self.engine.step(step_name).get("next_step")
        if next_step in {None,"END"}: return {"status":"END"}
        if next_step=="ROUTE_DEPENDENT": next_step=self.engine.resolve_route_dependent(self.con,self.project_id)
        if next_step=="ROUTE_SELECTION": return {"status":"WAITING_ROUTE","prompt":"A / B を指定してください。"}
        if next_step=="SELECTION_CONFIRM" and get_directive(self.con,self.project_id,"RANK_SELECTION") is None: return {"status":"WAITING_RANK_SELECTION","prompt":"何位を使いますか？"}
        if next_step=="PRODUCTION":
            if get_directive(self.con,self.project_id,"BGM_POLICY") is None: return {"status":"WAITING_BGM","prompt":"BGMは ①なし ②fixed_bgm ③ASMR のどれにしますか？"}
            if self._resolve_audio_policy_if_possible() is None and get_directive(self.con,self.project_id,"AUDIO_POLICY") is None: return {"status":"WAITING_AUDIO_POLICY","prompt":"元音声の扱いを指定してください。"}
        return self.execute(next_step,**kwargs)

    def handle_user_command(self, text:str, **kwargs:Any) -> dict[str,Any]:
        cmd=parse_command(text); intent=cmd["intent"]
        if intent=="APPROVE":
            row=self.con.execute("SELECT * FROM gates WHERE project_id=? AND status='OPEN'",(self.project_id,)).fetchone()
            if not row: raise RuntimeError("NO_OPEN_GATE")
            source_step=self._step_for_gate_stage(row["stage"]); decision=self.approve_open_gate(decision="APPROVE")
            return {"command":cmd,"decision":decision,"next":self._execute_next_after(source_step,**kwargs)}
        if intent=="RANK_SELECTION": return {"command":cmd,"next":self.execute("SELECTION_CONFIRM",ranks=cmd["ranks"],**kwargs)}
        if intent=="ROUTE":
            self.execute("ROUTE_SELECTION",route=cmd["route"]); return {"command":cmd,"next":self.execute("CTA",cta_none=bool(cmd.get("cta_none")),**kwargs)}
        if intent=="BGM":
            set_directive(self.con,self.project_id,"BGM_POLICY",cmd["value"])
            if self._resolve_audio_policy_if_possible() is None and get_directive(self.con,self.project_id,"AUDIO_POLICY") is None: return {"command":cmd,"status":"WAITING_AUDIO_POLICY"}
            return {"command":cmd,"next":self.execute("PRODUCTION",**kwargs)}
        if intent=="PUBLISHING": return {"command":cmd,"next":self.execute(self.engine.resolve_route_dependent(self.con,self.project_id),**kwargs)}
        if intent=="BASE_COPY": return {"command":cmd,"next":self.execute("BASE_COPY",**kwargs)}
        if intent=="BASE_IMAGES": return {"command":cmd,"next":self.execute("BASE_IMAGES",**kwargs)}
        if intent=="THUMBNAIL_BG": return {"command":cmd,"next":self.execute("THUMBNAIL_BG",**kwargs)}
        if intent=="THUMBNAIL_TEXT": return {"command":cmd,"next":self.execute("THUMBNAIL_TEXT",**kwargs)}
        if intent=="THUMBNAIL_NEXT":
            step="THUMBNAIL_TEXT" if get_approved(self.con,self.project_id,"THUMBNAIL_BG") else "THUMBNAIL_BG"; return {"command":cmd,"next":self.execute(step,**kwargs)}
        if intent=="FINAL": return {"command":cmd,"next":self.execute("FINAL",**kwargs)}
        if intent=="SUBTITLE_HELPER":
            for slot in ["SCRIPT_FINAL","CTA_SCRIPT","TIPS_SCRIPT","SCRIPT_DRAFT"]:
                art=get_candidate(self.con,self.project_id,slot) or get_approved(self.con,self.project_id,slot,allow_pending=True)
                if art:
                    try:
                        data=json.loads(Path(art["path"]).read_text(encoding="utf-8")); return {"command":cmd,"artifact":art,"text":data.get("display_text") or data.get("text")}
                    except Exception: pass
            return {"command":cmd,"status":"NO_SUBTITLE_ARTIFACT"}
        if intent=="RESET":
            new_id=f"{self.project_id}_restart_{uuid.uuid4().hex[:6]}"; from .db import create_project; create_project(self.con,new_id,None); self.project_id=new_id
            return {"command":cmd,"status":"RESET","project_id":new_id}
        if intent=="START_OR_NEXT":
            open_gate_row=self.con.execute("SELECT gate_id,stage FROM gates WHERE project_id=? AND status='OPEN'",(self.project_id,)).fetchone()
            if open_gate_row: return {"command":cmd,"status":"WAITING_APPROVAL","gate":dict(open_gate_row)}
            analysis=get_candidate(self.con,self.project_id,"ANALYSIS")
            if not analysis:
                src=latest_asset(self.con,self.project_id,"MAIN_SOURCE")
                if not src: return {"command":cmd,"status":"MAIN_SOURCE_REQUIRED"}
                return {"command":cmd,"next":self.execute("VIDEO_ANALYSIS",source_path=src["path"],**kwargs)}
            if get_approved(self.con,self.project_id,"ANALYSIS") and not get_candidate(self.con,self.project_id,"RANKING"): return {"command":cmd,"next":self.execute("RESEARCH_RANKING",**kwargs)}
            if get_candidate(self.con,self.project_id,"RANKING") and get_directive(self.con,self.project_id,"RANK_SELECTION") is None: return {"command":cmd,"status":"WAITING_RANK_SELECTION","prompt":"何位を使いますか？"}
            return {"command":cmd,"status":"NO_AUTOMATIC_NEXT","state":self.status()["state"]}
        return {"command":cmd,"status":"TEXT_NOT_ROUTED","text":cmd.get("text")}

    def import_user_asset(self, role:str, path:str|Path, metadata:dict[str,Any]|None=None) -> dict[str,Any]:
        from .assets import import_asset; from .db import create_project
        if role!="MAIN_SOURCE": return {"project_id":self.project_id,"new_project":False,"asset":import_asset(self.con,project_id=self.project_id,role=role,path=path,metadata=metadata)}
        try:
            art=import_asset(self.con,project_id=self.project_id,role=role,path=path,metadata=metadata); return {"project_id":self.project_id,"new_project":False,"asset":art}
        except RuntimeError as exc:
            if str(exc)!="NEW_PROJECT_REQUIRED": raise
            sha=sha256_file(path); base=self.project_id.split("_src_")[0]; new_id=f"{base}_src_{sha[:8]}"
            row=self.con.execute("SELECT project_id,main_source_sha256 FROM projects WHERE project_id=?",(new_id,)).fetchone()
            if row is None: create_project(self.con,new_id,None)
            elif row["main_source_sha256"] not in {None,sha}: new_id=f"{base}_src_{sha[:8]}_{uuid.uuid4().hex[:4]}"; create_project(self.con,new_id,None)
            self.project_id=new_id; art=import_asset(self.con,project_id=new_id,role=role,path=path,metadata=metadata)
            return {"project_id":new_id,"new_project":True,"asset":art}

    def status(self)->dict[str,Any]:
        state=get_state(self.con,self.project_id); slots=[dict(r) for r in self.con.execute("SELECT * FROM artifact_slots WHERE project_id=? ORDER BY slot",(self.project_id,)).fetchall()]
        directives={r["directive_type"]:json.loads(r["value_json"]) for r in self.con.execute("SELECT directive_type,value_json FROM directives WHERE project_id=? AND active=1",(self.project_id,)).fetchall()}
        return {"state":state,"slots":slots,"directives":directives}
