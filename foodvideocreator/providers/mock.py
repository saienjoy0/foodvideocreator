from __future__ import annotations

import json
import math
import wave
from pathlib import Path
from typing import Any
from PIL import Image

from .base import AIProvider, VoiceProvider, ImageProvider


class MockAIProvider(AIProvider):
    def video_semantic_analysis(self, payload: dict[str, Any]) -> dict[str, Any]:
        return {"dish_identity": payload.get("dish_name") or "テスト料理", "dish_identity_confidence": 0.95, "identity_basis": ["mock input"], "identity_conflict": False, "major_scenes": [{"start":0.0,"end":float((payload.get("video_info") or {}).get("duration",1.0)),"description":"料理の主要映像"}], "facts_visible": ["料理が映っている"], "facts_unconfirmed": ["味・歴史・原材料"], "audio": {"human_speech_present": False, "language": None, "asmr_present": False}, "source_preprocess": {"burned_in_subtitle": False, "logo": False, "ui": False, "black_frame": False, "video_corruption": False, "subtitle_removal_risk": "PASS"}}

    def research_and_rank(self, payload: dict[str, Any]) -> dict[str, Any]:
        dish = payload.get("dish_identity", "料理")
        claims = [
            {"claim_id": "story_1", "claim_type": "STORY", "claim": f"{dish}には語り継がれる由来がある", "classification": "legend", "evidence_strength": "medium", "sources": [{"source_id": "mock1", "publisher": "mock", "source_title": "mock source", "source_type": "reference", "position": "supports", "evidence_summary": "mock evidence", "url": "", "retrieved_at": ""}]},
            {"claim_id": "context_1", "claim_type": "CONTEXT", "claim": f"{dish}がどんな料理かを初見向けに説明する", "classification": "general_characteristic", "evidence_strength": "medium", "sources": [{"source_id": "mock2", "publisher": "mock", "source_title": "mock source", "source_type": "reference", "position": "supports", "evidence_summary": "mock evidence", "url": "", "retrieved_at": ""}]},
        ]
        return {"claims": claims, "ranking": [{"rank": 1, "claim_id": "story_1", "point_name": "由来", "why_interesting": "意外性", "short_line": "意外な由来", "classification": "legend"}]}

    def script_lab(self, payload: dict[str, Any]) -> dict[str, Any]:
        seconds = float(payload.get("video_seconds", 30)); low = math.ceil(seconds * 8); high = math.floor(seconds * 9)
        phrases = ["見た目だけでは分からない背景がある。", "何の料理か分かると映像の意味が変わる。", "由来として伝わる話には当時の事情が残る。", "伝説と史実を分けると意外な点が見える。", "工程と背景知識がつながると一度で理解しやすい。", "現在も独特の作り方が見どころになっている。"]
        text = ""; import unicodedata
        def eff(x): return sum(1 for c in x if not c.isspace() and not unicodedata.category(c).startswith(("P","Z")))
        i=0
        while eff(text) < low:
            remaining=high-eff(text); ph=phrases[i % len(phrases)]
            if eff(ph) <= remaining: text += ph
            else:
                chars=[]
                for ch in ph:
                    chars.append(ch)
                    if eff("".join(chars)) >= remaining: break
                text += "".join(chars)
            i+=1
            if i>100: break
        selection=payload.get("selection",{}); used=[c.get("claim_id") for c in (selection.get("story_claims",[])+selection.get("context_claims",[])) if c.get("claim_id")]
        duration=float(payload.get("video_seconds",30)); beat_edges=[0.0,duration/3,duration*2/3,duration]
        beat_map=[{"beat_id":f"beat_{j+1}","start_sec":beat_edges[j],"end_sec":beat_edges[j+1],"claim_ids":used,"new_information":["料理の正体","由来","結果"][j],"narrative_role":["hook","cause","payoff"][j]} for j in range(3)]
        hooks=[f"見た目からは想像できない由来がある{i}" for i in range(1,7)]
        return {"angles": ["Gap", "Origin", "Problem/Solution"], "hooks": hooks, "drafts": [{"id":"draft_a","text":text},{"id":"draft_b","text":text}], "pairwise_result":{"winner_id":"draft_a","reason":"初見理解と因果が明確"},"rewrite_count":1,"beat_map":beat_map,"selected_text": text, "tips_text": text, "final_text": text, "used_claim_ids":used,"critics":{"viewer":{"pass":True},"shorts_editor":{"pass":True},"fact":{"pass":True}},"hook_payoff": {"status": "CLOSED","payoff_claim_ids":used}}

    def cta(self, payload: dict[str, Any]) -> dict[str, Any]:
        text=payload.get("text",""); route=payload.get("route","A")
        if payload.get("cta_none"): return {"text":text,"policy":"NONE"}
        cta="初めて知ったらいいねしてね。" if route=="A" else "気になったら概要欄を見てね。"
        import unicodedata
        def eff(x): return sum(1 for c in x if not c.isspace() and not unicodedata.category(c).startswith(("P","Z")))
        need=eff(cta); chars=list(text); removed=0
        while chars and removed<need:
            ch=chars.pop()
            if not ch.isspace() and not unicodedata.category(ch).startswith(("P","Z")): removed+=1
        out="".join(chars).rstrip("。！？!?、 ")+"。"+cta
        return {"text":out,"policy":"LIKE_FOLLOW" if route=="A" else "BASE"}

    def align_audio(self, payload: dict[str, Any]) -> dict[str, Any]:
        text=payload.get("text",""); duration=float(payload.get("duration",1.0)); import re
        parts=[p.strip() for p in re.split(r"(?<=[。！？!?])|\n+",text) if p.strip()] or [text]
        weights=[max(1,len(p)) for p in parts]; total=sum(weights); cur=0.0; cues=[]
        for p,w in zip(parts,weights):
            span=duration*w/total; cues.append({"start":max(0,cur-.15),"end":min(duration,cur+span),"text":p}); cur+=span
        return {"result":"PASS","cues":cues,"method":"mock_length_alignment"}

    def publishing(self, payload: dict[str, Any]) -> dict[str, Any]:
        route = payload.get("route", "A"); title = "見た目だけじゃ分からない中国グルメ😳"
        if route == "B": body = "見た目はシンプルでも、背景を知ると印象が変わる一皿です🍜✨\n動画では料理の正体と、語り継がれてきた由来を初見向けに紹介しています。\n気になった人は、食卓で楽しめる中国グルメもゆっくりチェックしてみてください👇\nhttps://pecopeco.theshop.jp/\n#中国グルメ #グルメ豆知識 #中華料理 #料理好き #食文化 #Shorts"
        else: body = "見た目はシンプルでも、背景を知ると印象が変わる一皿です🍜✨\n動画では料理の正体と、語り継がれてきた由来を初見向けに紹介しています。\n作り方だけでなく、なぜ生まれたのかまで分かると映像の見え方も変わります👀\n#中国グルメ #グルメ豆知識 #中華料理 #料理好き #食文化 #Shorts"
        claim_ids=[c.get("claim_id") for c in ((payload.get("claims") or {}).get("claims") or []) if c.get("claim_id")]
        return {"title": title, "description": body, "fact_check":{"used_claim_ids":claim_ids[:2],"new_fact_detected":False}}

    def base_copy(self, payload: dict[str, Any]) -> dict[str, Any]:
        info=payload.get("product_info") or {}
        return {"product_name": payload.get("product_name", "中国グルメ商品"), "description": "確認済み情報だけで構成した商品説明です。", "internal_checks": ["内容量・原材料・賞味期限を出品前に確認"], "used_product_fields":sorted(info.keys()), "unverified_product_fields":[]}

    def semantic_video_qa(self, payload: dict[str, Any]) -> dict[str, Any]: return {"result": "PASS", "checks": {"script_meaning_match": True, "no_unapproved_addition": True, "dish_identity": True}}
    def thumbnail_copy(self, payload: dict[str, Any]) -> dict[str, Any]:
        used=[c.get("claim_id") for c in (payload.get("approved_claims") or []) if c.get("claim_id")][:1]
        return {"line1": "中国の料理", "line2": "まさかの由来!?", "line3": "知ると驚く", "used_claim_ids":used, "new_fact_detected":False}
    def image_semantic_qa(self, payload: dict[str, Any]) -> dict[str, Any]: return {"result":"PASS","text_zero":True,"logo_zero":True,"watermark_zero":True,"ui_zero":True,"no_mosaic":True,"no_black_band":True,"dish_large":True,"same_dish":True,"small_readability":True}


class MockVoiceProvider(VoiceProvider):
    def synthesize(self, text: str, output_path: Path, profile: dict[str, Any]) -> dict[str, Any]:
        rate = float(profile.get("chars_per_second", 7.5)); duration = max(0.5, len(text) / rate); sr = 24000; frames = int(duration * sr)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with wave.open(str(output_path), "wb") as wf:
            wf.setnchannels(1); wf.setsampwidth(2); wf.setframerate(sr); wf.writeframes(b"\x00\x00" * frames)
        return {"duration": duration, "sample_rate": sr}


class MockImageProvider(ImageProvider):
    def reconstruct_food_background(self, source_path: Path, output_path: Path, payload: dict[str, Any]) -> dict[str, Any]:
        im = Image.open(source_path).convert("RGB"); im = im.resize((1080, 1920)); output_path.parent.mkdir(parents=True, exist_ok=True); im.save(output_path)
        return {"mode": "B", "mock": True}
