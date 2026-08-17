from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from ..artifacts import project_artifact_root, commit_file_artifact, get_approved, get_candidate
from ..checks import record_check, latest_check_passes
from ..fonts import TARGET_FULL_NAME
from ..media import append_thumbnail, verify_decode, compare_video_body, audio_content_md5


def _require_thumbnail_evidence(con, project_id: str, bg: dict, thumb: dict) -> dict[str, Any]:
    required_bg=["CHECK_THUMBNAIL_BG"]
    required_thumb=["CHECK_FONT_FULL_NAME","CHECK_BBOX","CHECK_270_PREVIEW","CHECK_REAL_FONT_COMPOSITE"]
    missing=[c for c in required_bg if not latest_check_passes(con,project_id,c,bg["artifact_id"])]
    missing += [c for c in required_thumb if not latest_check_passes(con,project_id,c,thumb["artifact_id"])]
    manifest_art=get_candidate(con,project_id,"THUMBNAIL_TEXT_MANIFEST")
    if not manifest_art:
        missing.append("THUMBNAIL_TEXT_MANIFEST")
        manifest={}
    else:
        manifest=json.loads(Path(manifest_art["path"]).read_text(encoding="utf-8"))
        if manifest.get("thumbnail_sha256")!=thumb["sha256"]: missing.append("THUMBNAIL_MANIFEST_SHA")
        if manifest.get("background_sha256")!=bg["sha256"]: missing.append("THUMBNAIL_BACKGROUND_SHA")
        if manifest.get("font_name")!=TARGET_FULL_NAME: missing.append("THUMBNAIL_FONT_NAME")
        if manifest.get("small_readability")!="PASS": missing.append("THUMBNAIL_SMALL_READABILITY")
        if manifest.get("real_font_composite") is not True: missing.append("THUMBNAIL_REAL_FONT")
        for key in [
            "font_size_line1","font_size_line2","font_size_line3",
            "stroke_line1","stroke_line2","stroke_line3",
            "horizontal_scale_line1","horizontal_scale_line2","horizontal_scale_line3",
            "bbox_line1","bbox_line2","bbox_line3",
        ]:
            if key not in manifest: missing.append(key)
    if missing:
        raise RuntimeError("FINAL_THUMBNAIL_EVIDENCE_MISSING:"+",".join(missing))
    return {"manifest_artifact_id":manifest_art["artifact_id"],"manifest":manifest}


def run_final(con, *, project_id:str, artifact_root:str|Path, run_id:str|None=None, rule_bundle:dict[str,Any]|None=None)->dict[str,Any]:
    video=get_approved(con,project_id,"VIDEO_CANDIDATE")
    bg=get_approved(con,project_id,"THUMBNAIL_BG")
    thumb=get_approved(con,project_id,"THUMBNAIL_TEXT")
    if not video or not bg or not thumb: raise RuntimeError("FINAL_APPROVALS_REQUIRED")
    evidence=_require_thumbnail_evidence(con,project_id,bg,thumb)
    work=project_artifact_root(artifact_root,project_id)/".work"; out=work/"final_video.mp4"
    result=append_thumbnail(video["path"],thumb["path"],out)
    art=commit_file_artifact(
        con,project_id=project_id,artifact_type="FINAL_VIDEO",source_path=out,artifact_root=artifact_root,slot="FINAL_VIDEO",created_by_run_id=run_id,
        dependencies=[(video["artifact_id"],video["sha256"]),(thumb["artifact_id"],thumb["sha256"])],
        metadata={"thumbnail_frames":result["thumbnail_frames"],"thumbnail_sha256":thumb["sha256"],"source_video_sha256":video["sha256"],"thumbnail_manifest_artifact_id":evidence["manifest_artifact_id"],"mode":result["mode"]}
    )
    decode=verify_decode(art["path"])
    body=compare_video_body(video["path"],art["path"],work/"final_body_compare",black_tail_start=result.get("black_tail_start"))
    src_audio_md5=audio_content_md5(video["path"]); final_audio_md5=audio_content_md5(art["path"])
    audio_match=src_audio_md5==final_audio_md5
    record_check(con,project_id,"CHECK_FINAL_SHA",artifact_id=art["artifact_id"],artifact_sha256=art["sha256"],measurement={"used_thumbnail_sha256":thumb["sha256"],"approved_thumbnail_sha256":thumb["sha256"],"manifest_sha256":evidence["manifest"].get("thumbnail_sha256")},result="PASS")
    record_check(con,project_id,"CHECK_FINAL_DECODE",artifact_id=art["artifact_id"],artifact_sha256=art["sha256"],measurement=decode,result=decode["result"])
    record_check(con,project_id,"CHECK_FINAL_BODY_UNCHANGED",artifact_id=art["artifact_id"],artifact_sha256=art["sha256"],measurement=body,result=body["result"])
    record_check(con,project_id,"CHECK_FINAL_AUDIO_UNCHANGED",artifact_id=art["artifact_id"],artifact_sha256=art["sha256"],measurement={"source_audio_md5":src_audio_md5,"final_audio_md5":final_audio_md5},result="PASS" if audio_match else "FAIL")
    if decode["result"]!="PASS" or body["result"]!="PASS" or not audio_match:
        raise RuntimeError("FINAL_QA_FAIL")
    result["body_compare"]=body; result["audio_content_md5_match"]=audio_match; result["thumbnail_evidence"]=evidence
    return {"artifact":art,"qa":result}
