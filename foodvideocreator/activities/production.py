from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from ..artifacts import project_artifact_root, commit_file_artifact, get_approved, write_json_artifact, find_fresh_by_fingerprint, set_candidate
from ..assets import latest_asset
from ..checks import record_check
from ..directives import get_directive
from ..media import audio_duration, ffprobe, render_with_ass, verify_decode
from ..providers.base import AIProvider, VoiceProvider
from ..runs import fingerprint
from ..subtitles import build_ass, evenly_time_texts, render_design_previews, normalize_cues, validate_cue_timing


def create_production_plan(con, *, project_id: str, artifact_root: str|Path, run_id: str|None=None) -> dict[str,Any]:
    audio_policy=get_directive(con,project_id,"AUDIO_POLICY")
    bgm_policy=get_directive(con,project_id,"BGM_POLICY")
    if audio_policy is None: raise RuntimeError("AUDIO_POLICY_REQUIRED")
    if bgm_policy is None: raise RuntimeError("BGM_POLICY_REQUIRED")
    if audio_policy in {"REPLACE_SPEECH","DUCK_ORIGINAL_SPEECH"}: mode="GENERATED_JA_VOICE"
    elif audio_policy=="NO_GENERATED_VOICE": mode="NO_GENERATED_VOICE"
    else: mode="EXISTING_JA_VOICE" if get_directive(con,project_id,"EXISTING_JA_VOICE",False) else "NO_GENERATED_VOICE"
    plan={"mode":mode,"audio_policy":audio_policy,"bgm_policy":bgm_policy,"voice_required":mode=="GENERATED_JA_VOICE","alignment_source":"generated_voice" if mode=="GENERATED_JA_VOICE" else "existing_audio" if mode=="EXISTING_JA_VOICE" else "estimated_timing","required_activities":["SUBTITLE","RENDER"]}
    if plan["voice_required"]: plan["required_activities"].insert(0,"VOICE")
    return write_json_artifact(con,project_id=project_id,artifact_type="PRODUCTION_PLAN",data=plan,artifact_root=artifact_root,slot="PRODUCTION_PLAN",filename="production_plan.json",created_by_run_id=run_id)


def _split_text(text:str)->list[str]:
    parts=[p.strip() for p in re.split(r"(?<=[。！？!?])|\n+",text) if p.strip()]
    return parts or [text.strip()]


def _bgm_config(con,project_id:str,assets_dir:str|Path="assets")->tuple[str|None,float|None]:
    policy=get_directive(con,project_id,"BGM_POLICY")
    if policy=="NONE": return None,None
    rows=con.execute("SELECT * FROM assets WHERE project_id=? AND role='BGM_ASSET' ORDER BY created_at DESC,rowid DESC",(project_id,)).fetchall()
    selected=None
    for row in rows:
        d=dict(row); meta=json.loads(d.get("metadata_json") or "{}")
        kind=meta.get("kind")
        if policy=="FIXED" and kind in {None,"FIXED"}: selected=d; break
        if policy=="ASMR" and kind=="ASMR": selected=d; break
    if not selected:
        candidate=Path(assets_dir)/("fixed_bgm.MP3" if policy=="FIXED" else "asmr bgm.MP3")
        if candidate.exists() and candidate.stat().st_size>0:
            return str(candidate), .5 if policy=="FIXED" else .2
        raise RuntimeError("FIXED_BGM_ASSET_REQUIRED" if policy=="FIXED" else "ASMR_BGM_ASSET_REQUIRED")
    return selected["path"], .5 if policy=="FIXED" else .2


def run_production(con, *, project_id:str, artifact_root:str|Path, provider:AIProvider, voice_provider:VoiceProvider, run_id:str|None=None, rule_bundle:dict[str,Any]|None=None, assets_dir:str|Path="assets") -> dict[str,Any]:
    source=latest_asset(con,project_id,"MAIN_SOURCE")
    analysis=get_approved(con,project_id,"ANALYSIS")
    required_preprocess_keys={"burned_in_subtitle","logo","ui","black_frame","video_corruption","subtitle_removal_risk"}
    preprocess={"burned_in_subtitle":None,"logo":None,"ui":None,"black_frame":None,"video_corruption":None,"subtitle_removal_risk":None,"audio_present":None}
    if analysis:
        adata=json.loads(Path(analysis["path"]).read_text(encoding="utf-8"))
        preprocess.update(adata.get("source_preprocess",{})); preprocess["audio_present"]=adata.get("video",{}).get("audio_present")
    missing=[k for k in sorted(required_preprocess_keys) if preprocess.get(k) is None]
    reason=None
    if not analysis or missing or preprocess.get("audio_present") is None:
        pre_result="BLOCKED"; reason="SOURCE_PREPROCESS_ANALYSIS_INCOMPLETE"
    elif preprocess.get("video_corruption") is True:
        pre_result="BLOCKED"; reason="SOURCE_VIDEO_CORRUPTION"
    elif preprocess.get("subtitle_removal_risk")=="USER_DECISION_REQUIRED":
        pre_result="BLOCKED"; reason="SOURCE_PREPROCESS_USER_DECISION_REQUIRED"
    elif preprocess.get("burned_in_subtitle") is True:
        pre_result="BLOCKED"; reason="SOURCE_PREPROCESS_REQUIRED"
    elif preprocess.get("subtitle_removal_risk") not in {"PASS","NONE","NOT_NEEDED"}:
        pre_result="BLOCKED"; reason="SOURCE_PREPROCESS_UNRESOLVED"
    else:
        pre_result="PASS"
    measurement={**preprocess,"missing_keys":missing,"block_reason":reason}
    record_check(con,project_id,"CHECK_SOURCE_PREPROCESS",artifact_id=analysis["artifact_id"] if analysis else None,artifact_sha256=analysis["sha256"] if analysis else None,measurement=measurement,result=pre_result)
    if pre_result!="PASS": raise RuntimeError(reason or "SOURCE_PREPROCESS_BLOCKED")
    lock=get_approved(con,project_id,"SCRIPT_LOCK") or __import__('foodvideocreator.artifacts',fromlist=['get_candidate']).get_candidate(con,project_id,"SCRIPT_LOCK")
    script=get_approved(con,project_id,"SCRIPT_FINAL")
    if not source or not lock or not script: raise RuntimeError("PRODUCTION_INPUTS_MISSING")
    plan_art=create_production_plan(con,project_id=project_id,artifact_root=artifact_root,run_id=run_id)
    plan=json.loads(Path(plan_art["path"]).read_text(encoding="utf-8"))
    info=ffprobe(source["path"])
    script_data=json.loads(Path(script["path"]).read_text(encoding="utf-8")); text=script_data["spoken_text"]
    work=project_artifact_root(artifact_root,project_id)/".work"; work.mkdir(parents=True,exist_ok=True)
    voice_path=None
    if plan["voice_required"]:
        voice_fp=fingerprint({"script_sha":script["sha256"],"audio_policy":plan["audio_policy"],"chars_per_second":10.0,"rule_bundle_sha":(rule_bundle or {}).get("sha256")})
        voice_art=find_fresh_by_fingerprint(con,project_id,"VOICE",voice_fp)
        if voice_art:
            voice_path=Path(voice_art["path"]); set_candidate(con,project_id,"VOICE",voice_art["artifact_id"])
        else:
            voice_path=work/"voice.wav"; voice_provider.synthesize(text,voice_path,{"chars_per_second":10.0})
        adur=audio_duration(voice_path); actual="PASS" if adur<=info["duration"] else "FAIL"
        record_check(con,project_id,"CHECK_ACTUAL_VOICE_DURATION",artifact_id=script["artifact_id"],artifact_sha256=script["sha256"],measurement={"actual_voice_duration":adur,"available":info["duration"],"reused":voice_art is not None},result=actual)
        if actual!="PASS": raise RuntimeError("SCRIPT_TIMING_CONFLICT")
        if voice_art is None:
            voice_art=commit_file_artifact(con,project_id=project_id,artifact_type="VOICE",source_path=voice_path,artifact_root=artifact_root,slot="VOICE",created_by_run_id=run_id,step_fingerprint=voice_fp,dependencies=[(script["artifact_id"],script["sha256"])])
    else:
        voice_art=None
        record_check(con,project_id,"CHECK_ACTUAL_VOICE_DURATION",artifact_id=script["artifact_id"],artifact_sha256=script["sha256"],measurement={"skipped_by_plan":True},result="PASS",blocking=False)
    align_duration=min(info["duration"], audio_duration(voice_path) if voice_path else info["duration"])
    if plan["mode"] in {"GENERATED_JA_VOICE","EXISTING_JA_VOICE"}:
        aligned=provider.align_audio({"text":script_data["display_text"],"audio_path":str(voice_path) if voice_path else source["path"],"duration":align_duration,"mode":plan["mode"],"rule_bundle":rule_bundle})
        cues=normalize_cues(aligned.get("cues",[]),align_duration)
        timing_source=aligned.get("method","provider_alignment")
    else:
        cues=evenly_time_texts(_split_text(script_data["display_text"]), align_duration)
        timing_source="estimated_no_voice"
    if not cues: raise RuntimeError("ALIGNMENT_FAILED")
    timing_qa=validate_cue_timing(cues,align_duration)
    if timing_qa["result"]!="PASS": raise RuntimeError("SUBTITLE_TIMING_FAIL")
    timing_art=write_json_artifact(con,project_id=project_id,artifact_type="ALIGNMENT",data={"cues":cues,"source":timing_source},artifact_root=artifact_root,slot="ALIGNMENT",filename="alignment.json",created_by_run_id=run_id)
    from ..media import sample_frames
    design_frames=sample_frames(source["path"],work/"subtitle_design_frames",points=[.15,.5,.75])
    preview_qa=render_design_previews(design_frames,cues,work/"subtitle_previews",width=info["width"],height=info["height"])
    record_check(con,project_id,"CHECK_SUBTITLE_DESIGN_PREVIEW",artifact_id=script["artifact_id"],artifact_sha256=script["sha256"],measurement=preview_qa,result=preview_qa["result"])
    if preview_qa["result"]!="PASS": raise RuntimeError("SUBTITLE_DESIGN_PREVIEW_FAIL")
    record_check(con,project_id,"CHECK_SUBTITLE_TIMING",artifact_id=timing_art["artifact_id"],artifact_sha256=timing_art["sha256"],measurement={"source":timing_source,**timing_qa},result=timing_qa["result"])
    ass=build_ass(cues,work/"subtitles.ass",width=info["width"],height=info["height"])
    subtitle_art=commit_file_artifact(con,project_id=project_id,artifact_type="SUBTITLE",source_path=ass,artifact_root=artifact_root,slot="SUBTITLE",created_by_run_id=run_id,dependencies=[(script["artifact_id"],script["sha256"]),(timing_art["artifact_id"],timing_art["sha256"])],metadata={"max_lines":2,"color":"#FFB300","anchor_y":.833,"safe_x":[.1,.9],"safe_y":[.62,.88]})
    bgm_path,bgm_volume=_bgm_config(con,project_id,assets_dir)
    output=work/"video_candidate.mp4"
    preserve_original=plan["audio_policy"]!="REPLACE_SPEECH" and info["audio_present"]
    render_with_ass(source["path"],subtitle_art["path"],output,voice_path=voice_path,bgm_path=bgm_path,bgm_volume=bgm_volume,preserve_original_audio=preserve_original)
    outinfo=ffprobe(output); dec=verify_decode(output)
    output_samples=sample_frames(output,work/"video_candidate_samples",points=[0.0,.25,.5,.75,.9,.95,max(0,1-.2/info["duration"]) if info["duration"] else 1.0,1.0])
    expected_audio = info["audio_present"] or bool(voice_path) or bool(bgm_path)
    machine_ok=(dec["result"]=="PASS" and outinfo["width"]==info["width"] and outinfo["height"]==info["height"]
        and abs(outinfo["fps"]-info["fps"])<.02 and abs(outinfo["duration"]-info["duration"])<.15
        and outinfo["frame_count"]==info["frame_count"] and outinfo["video_codec"]=="h264"
        and ((not expected_audio and not outinfo["audio_present"]) or (expected_audio and outinfo["audio_codec"]=="aac"))
        and len(output_samples)==8)
    video_art=commit_file_artifact(con,project_id=project_id,artifact_type="VIDEO_CANDIDATE",source_path=output,artifact_root=artifact_root,slot="VIDEO_CANDIDATE",created_by_run_id=run_id,dependencies=[(script["artifact_id"],script["sha256"]),(subtitle_art["artifact_id"],subtitle_art["sha256"]),(plan_art["artifact_id"],plan_art["sha256"])],metadata={"source_sha256":source["sha256"],"bgm_policy":plan["bgm_policy"],"audio_policy":plan["audio_policy"]})
    record_check(con,project_id,"CHECK_VIDEO_MACHINE",artifact_id=video_art["artifact_id"],artifact_sha256=video_art["sha256"],measurement={"source":info,"output":outinfo,"decode":dec["result"],"frame_count_match":outinfo["frame_count"]==info["frame_count"],"representative_frames":[str(p) for p in output_samples]},result="PASS" if machine_ok else "FAIL")
    sem=provider.semantic_video_qa({"video_path":video_art["path"],"script":script_data,"source_sha256":source["sha256"],"rule_bundle":rule_bundle})
    record_check(con,project_id,"CHECK_VIDEO_SEMANTIC",artifact_id=video_art["artifact_id"],artifact_sha256=video_art["sha256"],measurement=sem,result=sem.get("result","FAIL"))
    return {"video":video_art,"subtitle":subtitle_art,"alignment":timing_art,"production_plan":plan_art,"machine_qa":"PASS" if machine_ok else "FAIL","semantic_qa":sem.get("result")}


def import_existing_video(con, *, project_id:str, artifact_root:str|Path, provider:AIProvider, run_id:str|None=None, rule_bundle:dict[str,Any]|None=None)->dict[str,Any]:
    ext=latest_asset(con,project_id,"EXTERNAL_RENDER")
    if not ext: raise RuntimeError("EXTERNAL_RENDER_REQUIRED")
    info=ffprobe(ext["path"]); dec=verify_decode(ext["path"])
    art=commit_file_artifact(con,project_id=project_id,artifact_type="VIDEO_CANDIDATE",source_path=ext["path"],artifact_root=artifact_root,slot="VIDEO_CANDIDATE",created_by_run_id=run_id,metadata={"external_render":True,"source_asset_sha256":ext["sha256"]})
    machine="PASS" if dec["result"]=="PASS" and info["duration"]>0 else "FAIL"
    record_check(con,project_id,"CHECK_VIDEO_MACHINE",artifact_id=art["artifact_id"],artifact_sha256=art["sha256"],measurement={"video":info,"decode":dec["result"]},result=machine)
    sem=provider.semantic_video_qa({"video_path":art["path"],"external_render":True,"rule_bundle":rule_bundle})
    record_check(con,project_id,"CHECK_VIDEO_SEMANTIC_IF_REQUIRED",artifact_id=art["artifact_id"],artifact_sha256=art["sha256"],measurement=sem,result=sem.get("result","PASS"),blocking=False)
    return {"video":art,"machine_qa":machine,"semantic_qa":sem.get("result")}
