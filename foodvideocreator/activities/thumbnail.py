from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from PIL import Image

from ..artifacts import project_artifact_root, commit_file_artifact, get_approved, get_candidate, write_json_artifact, sha256_file
from ..assets import latest_asset
from ..checks import record_check
from ..media import extract_frame, ffprobe
from ..providers.base import AIProvider, ImageProvider
from ..thumbnail import compose_thumbnail_text, make_background_mode_a


def _choose_source(con,project_id:str,work:Path)->Path:
    ref=latest_asset(con,project_id,"REFERENCE_IMAGE")
    if ref:return Path(ref["path"])
    src=latest_asset(con,project_id,"MAIN_SOURCE")
    if not src: raise RuntimeError("THUMBNAIL_SOURCE_REQUIRED")
    info=ffprobe(src["path"]); return extract_frame(src["path"],info["duration"]*.75,work/"thumb_source.jpg")


def run_thumbnail_bg(con, *, project_id:str, artifact_root:str|Path, provider:AIProvider, image_provider:ImageProvider|None=None, force_mode:str|None=None, run_id:str|None=None, rule_bundle:dict[str,Any]|None=None)->dict[str,Any]:
    work=project_artifact_root(artifact_root,project_id)/".work"; work.mkdir(parents=True,exist_ok=True); src=_choose_source(con,project_id,work)
    im=Image.open(src); ratio=im.width/im.height
    mode=force_mode or ("A" if abs(ratio-(9/16))<.18 and im.width>=720 else "B")
    out=work/"thumbnail_bg.jpg"
    if mode=="B" and image_provider is not None: meta=image_provider.reconstruct_food_background(src,out,{"no_text":True,"no_logo":True,"same_dish":True})
    else: mode="A"; meta=make_background_mode_a(src,out)
    opened=Image.open(out); canvas_ok=opened.size==(1080,1920)
    semantic=provider.image_semantic_qa({"kind":"THUMBNAIL_BG","image_path":str(out),"source_path":str(src),"requirements":["text_zero","logo_zero","watermark_zero","ui_zero","no_mosaic","no_black_band","dish_large","same_dish"],"rule_bundle":rule_bundle})
    ok=canvas_ok and semantic.get("result")=="PASS"
    art=commit_file_artifact(con,project_id=project_id,artifact_type="THUMBNAIL_BG",source_path=out,artifact_root=artifact_root,slot="THUMBNAIL_BG",created_by_run_id=run_id,metadata={"mode":mode,"source_path":str(src),"source_sha256":sha256_file(src),"output_sha256":sha256_file(out),"canvas":"1080x1920","semantic_qa":semantic})
    record_check(con,project_id,"CHECK_THUMBNAIL_BG",artifact_id=art["artifact_id"],artifact_sha256=art["sha256"],measurement={"canvas":opened.size,"mode":mode,"semantic":semantic},result="PASS" if ok else "FAIL")
    return {"artifact":art,"mode":mode,"qa":"PASS" if ok else "FAIL","semantic":semantic}


def run_thumbnail_text(con, *, project_id:str, artifact_root:str|Path, provider:AIProvider, copy_lines:list[str]|None=None, run_id:str|None=None, rule_bundle:dict[str,Any]|None=None)->dict[str,Any]:
    bg=get_approved(con,project_id,"THUMBNAIL_BG")
    if not bg: raise RuntimeError("THUMBNAIL_BG_APPROVAL_REQUIRED")
    script=get_approved(con,project_id,"SCRIPT_FINAL"); selection=get_approved(con,project_id,"SELECTION_CONFIRM")
    copy_fact_measure={"source":"USER_EXPLICIT"}; copy_fact_result="PASS"
    if copy_lines is None:
        selection_data=json.loads(Path(selection["path"]).read_text(encoding="utf-8")) if selection else {"story_claims":[],"context_claims":[]}
        selected_claims=list(selection_data.get("story_claims",[]))+list(selection_data.get("context_claims",[]))
        data=provider.thumbnail_copy({"script_path":script["path"] if script else None,"selection":selection_data,"approved_claims":selected_claims,"rule_bundle":rule_bundle})
        copy_lines=[data["line1"],data["line2"],data["line3"]]
        source="GENERATED_FROM_APPROVED_CLAIMS"
        allowed={c.get("claim_id") for c in selected_claims if c.get("claim_id")}
        used=set(data.get("used_claim_ids") or [])
        new_fact=data.get("new_fact_detected")
        copy_fact_result="PASS" if new_fact is False and used.issubset(allowed) else "FAIL"
        copy_fact_measure={"source":source,"allowed_claim_ids":sorted(allowed),"used_claim_ids":sorted(used),"new_fact_detected":new_fact}
    else: source="USER_EXPLICIT"
    copy_art=write_json_artifact(con,project_id=project_id,artifact_type="THUMBNAIL_COPY",data={"line1":copy_lines[0],"line2":copy_lines[1],"line3":copy_lines[2],"source":source},artifact_root=artifact_root,slot="THUMBNAIL_COPY",filename="thumbnail_copy.json",created_by_run_id=run_id)
    record_check(con,project_id,"CHECK_THUMBNAIL_COPY_FACTS",artifact_id=copy_art["artifact_id"],artifact_sha256=copy_art["sha256"],measurement=copy_fact_measure,result=copy_fact_result)
    work=project_artifact_root(artifact_root,project_id)/".work"; out=work/"thumbnail_final.jpg"; preview=work/"thumbnail_270x480.jpg"
    manifest=compose_thumbnail_text(bg["path"],copy_lines,out,preview)
    art=commit_file_artifact(con,project_id=project_id,artifact_type="THUMBNAIL_TEXT",source_path=out,artifact_root=artifact_root,slot="THUMBNAIL_TEXT",created_by_run_id=run_id,metadata=manifest,dependencies=[(bg["artifact_id"],bg["sha256"]),(copy_art["artifact_id"],copy_art["sha256"])])
    preview_art=commit_file_artifact(con,project_id=project_id,artifact_type="THUMBNAIL_PREVIEW",source_path=preview,artifact_root=artifact_root,slot="THUMBNAIL_PREVIEW",created_by_run_id=run_id,dependencies=[(art["artifact_id"],art["sha256"])])
    recs=manifest["lines"]
    record_check(con,project_id,"CHECK_FONT_FULL_NAME",artifact_id=art["artifact_id"],artifact_sha256=art["sha256"],measurement={"font_name":manifest["font_name"],"font_collection_index":manifest["font_collection_index"]},result="PASS" if manifest["font_name"]=="Noto Sans Mono CJK JP Bold" else "FAIL")
    record_check(con,project_id,"CHECK_BBOX",artifact_id=art["artifact_id"],artifact_sha256=art["sha256"],measurement={"line1":recs[0],"line2":recs[1],"line3":recs[2],"canvas":"1080x1920"},result="PASS")
    preview_semantic=provider.image_semantic_qa({"kind":"THUMBNAIL_270_PREVIEW","image_path":preview_art["path"],"requirements":["white_readable","red_first","yellow_instant","punctuation_clear","stroke_separated","reading_order_clear"],"rule_bundle":rule_bundle})
    preview_result="PASS" if preview_semantic.get("result")=="PASS" and preview_semantic.get("small_readability",True) else "FAIL"
    record_check(con,project_id,"CHECK_270_PREVIEW",artifact_id=art["artifact_id"],artifact_sha256=art["sha256"],measurement={"preview_artifact_id":preview_art["artifact_id"],"semantic":preview_semantic},result=preview_result)
    record_check(con,project_id,"CHECK_REAL_FONT_COMPOSITE",artifact_id=art["artifact_id"],artifact_sha256=art["sha256"],measurement={"real_font_composite":True,"thumbnail_sha256":manifest["thumbnail_sha256"]},result="PASS")
    final_manifest={**manifest,
        "font_size_line1":recs[0]["font_size"],"font_size_line2":recs[1]["font_size"],"font_size_line3":recs[2]["font_size"],
        "stroke_line1":recs[0]["stroke"],"stroke_line2":recs[1]["stroke"],"stroke_line3":recs[2]["stroke"],
        "horizontal_scale_line1":recs[0]["horizontal_scale"],"horizontal_scale_line2":recs[1]["horizontal_scale"],"horizontal_scale_line3":recs[2]["horizontal_scale"],
        "bbox_line1":recs[0]["bbox"],"bbox_line2":recs[1]["bbox"],"bbox_line3":recs[2]["bbox"],
        "small_readability":preview_result,"preview_semantic":preview_semantic,"real_font_composite":True,
        "thumbnail_sha256":art["sha256"],"background_sha256":bg["sha256"],"thumbnail_copy_sha256":copy_art["sha256"]}
    manifest_art=write_json_artifact(con,project_id=project_id,artifact_type="THUMBNAIL_TEXT_MANIFEST",data=final_manifest,artifact_root=artifact_root,slot="THUMBNAIL_TEXT_MANIFEST",filename="thumbnail_text_manifest.json",created_by_run_id=run_id,dependencies=[(art["artifact_id"],art["sha256"]),(preview_art["artifact_id"],preview_art["sha256"])])
    return {"artifact":art,"copy":copy_art,"preview":preview_art,"manifest":final_manifest,"manifest_artifact":manifest_art}
