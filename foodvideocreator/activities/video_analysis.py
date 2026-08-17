from __future__ import annotations

from pathlib import Path
from typing import Any

from ..artifacts import write_json_artifact, project_artifact_root
from ..checks import dish_identity_result, record_check
from ..editorial import attention_segments_result, ensure_scene_ids
from ..media import ffprobe, sample_frames, verify_decode
from ..providers.base import AIProvider


def run_video_analysis(con, *, project_id: str, source_path: str | Path, artifact_root: str | Path, provider: AIProvider, dish_name: str | None = None, run_id: str | None = None, rule_bundle: dict[str,Any] | None = None) -> dict[str, Any]:
    source_path=Path(source_path)
    info=ffprobe(source_path)
    frames=sample_frames(source_path, project_artifact_root(artifact_root,project_id)/"analysis_frames")
    semantic=provider.video_semantic_analysis({"dish_name":dish_name,"video_path":str(source_path),"video_info":info,"sample_frames":[str(p) for p in frames],"rule_bundle":rule_bundle})
    analysis={"video":info,"full_decode":verify_decode(source_path),"sample_frames":[str(p) for p in frames],**semantic}

    scene_ids=ensure_scene_ids(analysis)
    attention=attention_segments_result(analysis.get("attention_segments"),float(info.get("duration",0) or 0),set(scene_ids))
    if attention.get("segments"):
        analysis["attention_segments"]=attention["segments"]

    art=write_json_artifact(con,project_id=project_id,artifact_type="ANALYSIS",data=analysis,artifact_root=artifact_root,slot="ANALYSIS",filename="analysis.json",created_by_run_id=run_id,metadata={"rule_bundle_sha":(rule_bundle or {}).get("sha256")})
    result=dish_identity_result(float(analysis.get("dish_identity_confidence",0)),bool(analysis.get("identity_conflict",False)))
    record_check(con,project_id,"CHECK_DISH_IDENTITY",artifact_id=art["artifact_id"],artifact_sha256=art["sha256"],measurement={"confidence":analysis.get("dish_identity_confidence"),"identity_conflict":analysis.get("identity_conflict")},result=result)
    record_check(con,project_id,"CHECK_ATTENTION_SEGMENTS",artifact_id=art["artifact_id"],artifact_sha256=art["sha256"],measurement=attention,result=attention["result"])

    preprocess=analysis.get("source_preprocess") or {}
    required_pre={"burned_in_subtitle","logo","ui","black_frame","video_corruption","subtitle_removal_risk"}
    complete=(info.get("duration",0)>0 and info.get("fps",0)>0 and info.get("frame_count",0)>0 and info.get("width",0)>0 and info.get("height",0)>0
        and analysis.get("full_decode",{}).get("result")=="PASS" and bool(analysis.get("major_scenes"))
        and isinstance(analysis.get("facts_visible"),list) and isinstance(analysis.get("facts_unconfirmed"),list)
        and isinstance(analysis.get("audio"),dict) and required_pre.issubset(preprocess)
        and attention["result"]=="PASS")
    record_check(con,project_id,"CHECK_VIDEO_ANALYSIS_COMPLETE",artifact_id=art["artifact_id"],artifact_sha256=art["sha256"],measurement={"major_scene_count":len(analysis.get("major_scenes") or []),"facts_visible":len(analysis.get("facts_visible") or []),"facts_unconfirmed":len(analysis.get("facts_unconfirmed") or []),"source_preprocess_keys":sorted(preprocess),"decode":analysis.get("full_decode",{}).get("result"),"attention_segments":attention},result="PASS" if complete else "FAIL")
    return {"artifact":art,"analysis":analysis,"dish_identity_check":result,"attention_segments_check":attention["result"],"analysis_complete":"PASS" if complete else "FAIL"}
