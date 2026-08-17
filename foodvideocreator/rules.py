from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

STEP_RULES={
    "VIDEO_ANALYSIS":["01_popular_shorts.txt","02_video_analysis.txt"],
    "RESEARCH_RANKING":["01_popular_shorts.txt","03_research_ranking.txt"],
    "SELECTION_CONFIRM":["04_selection.txt"],
    "SCRIPT_DRAFT":["05_script_draft.txt"],
    "TIPS":["06_tips.txt"],
    "CTA_A":["07A_cta.txt"],
    "CTA_B":["07B_cta.txt"],
    "SCRIPT_FINAL":["08_script_final.txt"],
    "PRODUCTION":["09_production.txt"],
    "PUBLISHING_A":["10A_publishing.txt"],
    "PUBLISHING_B":["10B_publishing.txt"],
    "BASE_COPY":["11B_base_copy.txt","11B_reference.txt"],
    "BASE_IMAGES":["12B_base_images.txt"],
    "THUMBNAIL_BG":["13A_thumbnail_bg.txt"],
    "THUMBNAIL_TEXT":["13B_thumbnail_text.txt"],
    "FINAL":["14_final.txt"],
}

def load_rule_bundle(rules_dir:str|Path, step:str, route:str|None=None)->dict[str,Any]:
    key=step
    if step=="CTA" and route in {"A","B"}: key=f"CTA_{route}"
    files=STEP_RULES.get(key,[])
    parts=[]; paths=[]
    for name in files:
        p=Path(rules_dir)/name
        if not p.exists(): raise FileNotFoundError(f"RULE_FILE_MISSING:{p}")
        txt=p.read_text(encoding="utf-8")
        parts.append(f"\n===== {name} =====\n{txt}")
        paths.append(str(p))
    text="".join(parts)
    sha=hashlib.sha256(text.encode("utf-8")).hexdigest()
    return {"step":step,"route":route,"files":paths,"text":text,"sha256":sha}
