from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any

from .contract import load_contract, validate_contract
from .directives import get_directive
from .fonts import find_font_face

REQUIRED_RULE_FILES = {
    "01_popular_shorts.txt", "02_video_analysis.txt", "03_research_ranking.txt",
    "04_selection.txt", "05_script_draft.txt", "06_tips.txt", "07A_cta.txt",
    "07B_cta.txt", "08_script_final.txt", "09_production.txt", "10A_publishing.txt",
    "10B_publishing.txt", "11B_base_copy.txt", "11B_reference.txt", "12B_base_images.txt",
    "13A_thumbnail_bg.txt", "13B_thumbnail_text.txt", "14_final.txt", "subtitle_helper.txt",
}

def validate_startup(*, contract_path: str | Path, rules_dir: str | Path, con=None, project_id: str | None=None, assets_dir: str | Path | None=None, step: str | None=None) -> dict[str, Any]:
    contract_path=Path(contract_path); rules_dir=Path(rules_dir); assets_dir=Path(assets_dir) if assets_dir else None
    checks=[]
    def add(name, ok, detail=None, blocking=True):
        checks.append({"name":name,"result":"PASS" if ok else "FAIL","detail":detail,"blocking":blocking})
    add("ffmpeg", shutil.which("ffmpeg") is not None, shutil.which("ffmpeg"))
    add("ffprobe", shutil.which("ffprobe") is not None, shutil.which("ffprobe"))
    try:
        contract=load_contract(contract_path); validate_contract(contract); add("workflow_contract",True,{"steps":len(contract["steps"])})
    except Exception as e:
        add("workflow_contract",False,str(e))
    present={p.name for p in rules_dir.glob("*.txt")} if rules_dir.exists() else set()
    missing=sorted(REQUIRED_RULE_FILES-present)
    add("rule_bundle_files",not missing,{"missing":missing,"count":len(present)})
    old=list(rules_dir.glob("13_Shortsサムネ*.txt")) if rules_dir.exists() else []
    add("legacy_thumbnail_conflict",not bool(old),{"forbidden":[str(p) for p in old]})
    if step=="THUMBNAIL_TEXT":
        try:
            font=find_font_face(target="Noto Sans Mono CJK JP Bold")
            add("thumbnail_font",True,{"path":str(font[0]),"index":font[1],"full_name":"Noto Sans Mono CJK JP Bold"})
        except Exception as e:
            add("thumbnail_font",False,str(e))
    if con is not None and project_id:
        bgm=get_directive(con,project_id,"BGM_POLICY")
        if bgm in {"FIXED","ASMR"}:
            kind="fixed_bgm" if bgm=="FIXED" else "asmr_bgm"
            row=con.execute("SELECT path FROM assets WHERE project_id=? AND role='BGM_ASSET' ORDER BY asset_id DESC",(project_id,)).fetchall()
            found=False; paths=[]
            for r in row:
                p=Path(r[0]); paths.append(str(p))
                if p.exists() and kind.lower() in p.name.lower(): found=True
            if not found and assets_dir:
                candidate=assets_dir/("fixed_bgm.MP3" if bgm=="FIXED" else "asmr bgm.MP3")
                found=candidate.exists(); paths.append(str(candidate))
            add(f"bgm_asset_{bgm.lower()}",found,{"searched":paths})
    blocking_failures=[c for c in checks if c["blocking"] and c["result"]!="PASS"]
    return {"result":"PASS" if not blocking_failures else "FAIL","checks":checks,"blocking_failures":blocking_failures}
