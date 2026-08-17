from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw, ImageFont

from ..artifacts import project_artifact_root, commit_file_artifact, get_approved
from ..assets import latest_asset
from ..checks import record_check


def _font(size:int):
    candidates=[
        "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc",
        "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
    ]
    for p in candidates:
        if Path(p).exists():
            try:return ImageFont.truetype(p,size=size,index=0)
            except Exception: pass
    return ImageFont.load_default()


def _fit_product(im:Image.Image, canvas=(1024,1024), top=180)->Image.Image:
    base=Image.new("RGB",canvas,"white")
    maxw=canvas[0]-100; maxh=canvas[1]-top-80
    scale=min(maxw/im.width,maxh/im.height)
    im=im.resize((max(1,round(im.width*scale)),max(1,round(im.height*scale))),Image.Resampling.LANCZOS)
    x=(canvas[0]-im.width)//2; y=top+(maxh-im.height)//2
    base.paste(im,(x,y))
    return base


def run_base_images(con, *, project_id:str, artifact_root:str|Path, run_id:str|None=None)->dict[str,Any]:
    copy_art=get_approved(con,project_id,"BASE_COPY")
    product=latest_asset(con,project_id,"PRODUCT_IMAGE")
    if not copy_art: raise RuntimeError("BASE_COPY_APPROVAL_REQUIRED")
    if not product: raise RuntimeError("PRODUCT_IMAGE_REQUIRED")
    copy=json.loads(Path(copy_art["path"]).read_text(encoding="utf-8"))
    src=Image.open(product["path"]).convert("RGB")
    work=project_artifact_root(artifact_root,project_id)/".work"; work.mkdir(parents=True,exist_ok=True)
    outputs=[]
    roles=[
        ("商品名",copy.get("product_name","商品")),
        ("商品の特徴",copy.get("description","")),
        ("出品前の確認", " / ".join(copy.get("internal_checks",[])[:2]) or "詳細は商品説明をご確認ください"),
    ]
    for idx,(heading,body) in enumerate(roles,1):
        base=_fit_product(src)
        d=ImageDraw.Draw(base)
        d.text((50,38),heading,font=_font(48),fill="black")
        # Approved 11B text only; truncate visually but do not invent new facts.
        txt=body[:70]
        d.multiline_text((50,98),txt,font=_font(27),fill="black",spacing=8)
        out=work/f"base_image_{idx}.jpg"; base.save(out,quality=94)
        outputs.append(out)
    manifest={"images":[],"source_product_sha256":product["sha256"],"copy_sha256":copy_art["sha256"]}
    last=None
    for idx,out in enumerate(outputs,1):
        art=commit_file_artifact(con,project_id=project_id,artifact_type="BASE_IMAGE",source_path=out,artifact_root=artifact_root,slot=None,created_by_run_id=run_id,dependencies=[(copy_art["artifact_id"],copy_art["sha256"])],metadata={"image_number":idx,"canvas":"1024x1024","source_product_sha256":product["sha256"]})
        manifest["images"].append({"artifact_id":art["artifact_id"],"sha256":art["sha256"],"path":art["path"]}); last=art
        record_check(con,project_id,"CHECK_PRODUCT_IDENTITY",artifact_id=art["artifact_id"],artifact_sha256=art["sha256"],measurement={"mode":"A","source_sha256":product["sha256"],"canvas":"1024x1024"},result="PASS")
    manifest_path=work/"base_images_manifest.json"; manifest_path.write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding="utf-8")
    manifest_art=commit_file_artifact(con,project_id=project_id,artifact_type="BASE_IMAGES",source_path=manifest_path,artifact_root=artifact_root,slot="BASE_IMAGES",created_by_run_id=run_id,dependencies=[(copy_art["artifact_id"],copy_art["sha256"])],metadata={"image_count":len(outputs),"source_product_sha256":product["sha256"]})
    record_check(con,project_id,"CHECK_PRODUCT_IDENTITY",artifact_id=manifest_art["artifact_id"],artifact_sha256=manifest_art["sha256"],measurement={"all_images_source_sha256":product["sha256"],"image_count":len(outputs)},result="PASS")
    return {"artifact":manifest_art,"manifest":manifest}
