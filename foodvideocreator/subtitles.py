from __future__ import annotations

from pathlib import Path
from typing import Iterable, Any


def ass_time(seconds: float) -> str:
    seconds = max(0.0, seconds); h = int(seconds // 3600); seconds -= h * 3600; m = int(seconds // 60); seconds -= m * 60; s = int(seconds); cs = int(round((seconds - s) * 100))
    if cs >= 100: s += 1; cs -= 100
    return f"{h}:{m:02d}:{s:02d}.{cs:02d}"


def split_two_lines(text: str, max_chars: int = 24) -> str:
    text = text.strip().replace("\n", "")
    if len(text) <= max_chars: return text
    center=len(text)/2; candidates=range(max(1,int(center)-6), min(len(text),int(center)+7)); cut=min(candidates,key=lambda i:abs(i-center))
    return text[:cut] + r"\N" + text[cut:]


def _subtitle_font_face():
    from .fonts import find_font_face
    try: return find_font_face(target="Noto Sans CJK JP Bold")
    except Exception: return Path("/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc"), 0


def layout_subtitle_cue(text: str, *, width: int, height: int) -> dict[str, Any]:
    from PIL import Image, ImageDraw, ImageFont
    font_path,index=_subtitle_font_face(); safe_w=round(width*.8); base=max(18,round(height*.055)); min_fs=max(12,round(height*.025)); split=split_two_lines(text, max_chars=max(8,round(22*width/1080))); lines=split.split(r"\N")[:2]
    probe=Image.new("RGB",(max(32,width),max(32,height)),"black"); d=ImageDraw.Draw(probe); fs=base
    while True:
        stroke=max(2,round(fs*.09)); font=ImageFont.truetype(str(font_path),size=fs,index=0 if index is None else index); bbs=[d.textbbox((0,0),ln,font=font,stroke_width=stroke) for ln in lines]; widths=[b[2]-b[0] for b in bbs]; heights=[b[3]-b[1] for b in bbs]
        if (max(widths) if widths else 0) <= safe_w: break
        if fs<=min_fs: return {"result":"FAIL","reason":"subtitle_too_wide_at_min_font","lines":lines,"font_size":fs,"stroke":stroke,"widths":widths,"safe_width":safe_w}
        fs=max(min_fs,fs-2)
    return {"result":"PASS","lines":lines,"text_ass":r"\N".join(lines),"font_size":fs,"stroke":stroke,"widths":widths,"heights":heights,"safe_width":safe_w,"font_path":str(font_path),"font_index":index}


def build_ass(cues: Iterable[dict], output: str | Path, *, width: int, height: int, font_name: str = "Noto Sans CJK JP", color: str = "&H0000B3FF") -> Path:
    output = Path(output); output.parent.mkdir(parents=True, exist_ok=True); base=max(18,round(height*.055)); base_outline=max(2,round(base*.09)); margin_v = round(height * (1 - .833))
    header = f"""[Script Info]\nScriptType: v4.00+\nPlayResX: {width}\nPlayResY: {height}\nScaledBorderAndShadow: yes\nWrapStyle: 2\n\n[V4+ Styles]\nFormat: Name,Fontname,Fontsize,PrimaryColour,SecondaryColour,OutlineColour,BackColour,Bold,Italic,Underline,StrikeOut,ScaleX,ScaleY,Spacing,Angle,BorderStyle,Outline,Shadow,Alignment,MarginL,MarginR,MarginV,Encoding\nStyle: Default,{font_name},{base},{color},{color},&H00000000,&H00000000,-1,0,0,0,100,100,0,0,1,{base_outline},0,2,{round(width*.1)},{round(width*.1)},{margin_v},1\n\n[Events]\nFormat: Layer,Start,End,Style,Name,MarginL,MarginR,MarginV,Effect,Text\n"""
    rows=[header]
    for cue in cues:
        layout=layout_subtitle_cue(str(cue["text"]),width=width,height=height)
        if layout["result"]!="PASS": raise RuntimeError(f"SUBTITLE_LAYOUT_FAIL:{layout}")
        override=f"{{\\fs{layout['font_size']}\\bord{layout['stroke']}}}"; rows.append(f"Dialogue: 0,{ass_time(float(cue['start']))},{ass_time(float(cue['end']))},Default,,0,0,0,,{override}{layout['text_ass']}\n")
    output.write_text("".join(rows),encoding="utf-8-sig"); return output


def evenly_time_texts(texts: list[str], duration: float, lead: float = 0.15) -> list[dict]:
    if not texts: return []
    weights = [max(1, len(t)) for t in texts]; total=sum(weights); cur=0.0; cues=[]
    for text,w in zip(texts,weights):
        span=duration*w/total; speech_start=cur; speech_end=min(duration,cur+span); start=max(0,speech_start-lead); cues.append({"start":start,"end":speech_end,"speech_start":speech_start,"speech_end":speech_end,"text":text}); cur+=span
    return normalize_cues(cues,duration)


def normalize_cues(cues: list[dict], duration: float) -> list[dict]:
    out=[]
    for raw in cues:
        c=dict(raw); c["start"]=max(0.0,float(c.get("start",0.0))); c["end"]=min(duration,float(c.get("end",duration)))
        if c["end"]<=c["start"]: c["end"]=min(duration,c["start"]+0.04)
        out.append(c)
    for i in range(1,len(out)):
        if out[i]["start"] < out[i-1]["end"]:
            boundary=float(out[i].get("speech_start",out[i]["start"])); boundary=max(out[i]["start"],min(out[i-1]["end"],boundary)); out[i-1]["end"]=boundary; out[i]["start"]=boundary
        if out[i-1]["end"]<=out[i-1]["start"]: out[i-1]["end"]=min(duration,out[i-1]["start"]+0.04)
    return out


def validate_cue_timing(cues: list[dict], duration: float) -> dict[str, Any]:
    issues=[]
    for i,c in enumerate(cues):
        start=float(c["start"]); end=float(c["end"])
        if not (0<=start<end<=duration+1e-3): issues.append({"index":i,"issue":"bounds","start":start,"end":end})
        if i and start < float(cues[i-1]["end"])-1e-4: issues.append({"index":i,"issue":"overlap"})
    return {"result":"PASS" if not issues else "FAIL","cue_count":len(cues),"issues":issues,"duration":duration}


def render_design_previews(frame_paths: list[str | Path], cues: list[dict], output_dir: str | Path, *, width: int, height: int) -> dict:
    from PIL import Image, ImageDraw, ImageFont
    output_dir=Path(output_dir); output_dir.mkdir(parents=True,exist_ok=True)
    if not frame_paths or not cues: return {"result":"FAIL","reason":"frames_or_cues_missing","previews":[]}
    font_path,index=_subtitle_font_face(); safe_x=(round(width*.1),round(width*.9)); safe_y=(round(height*.62),round(height*.88)); anchor_y=round(height*.833); longest=max(cues,key=lambda c:len(c.get("text",""))); selections=[longest,longest,cues[len(cues)//2]]; labels=["longest","two_line","complex_background"]; records=[]; overall=True
    for idx,(cue,label) in enumerate(zip(selections,labels)):
        frame=Image.open(frame_paths[min(idx,len(frame_paths)-1)]).convert("RGB").resize((width,height)); d=ImageDraw.Draw(frame); text=str(cue.get("text","")); layout=layout_subtitle_cue(text,width=width,height=height)
        if layout["result"]!="PASS": records.append({"label":label,"result":"FAIL","layout":layout}); overall=False; continue
        lines=list(layout["lines"])
        if label=="two_line" and len(lines)==1 and len(text)>1:
            cut=len(text)//2; lines=[text[:cut],text[cut:]]; forced=layout_subtitle_cue(r"\N".join(lines).replace(r"\N",""),width=width,height=height)
            if forced["result"]=="PASS": layout={**layout,"font_size":forced["font_size"],"stroke":forced["stroke"]}
        fs=int(layout["font_size"]); stroke=int(layout["stroke"]); font=ImageFont.truetype(str(font_path),size=fs,index=0 if index is None else index); bbs=[d.textbbox((0,0),ln,font=font,stroke_width=stroke) for ln in lines]; heights=[b[3]-b[1] for b in bbs]; block_h=sum(heights)+max(0,len(lines)-1)*round(fs*.15); y=anchor_y-block_h//2; y=min(y,safe_y[1]-block_h); y=max(y,safe_y[0]); x=width//2; bboxes=[]; cy=y
        for ln,bb,h in zip(lines,bbs,heights):
            tw=bb[2]-bb[0]; xx=round(x-tw/2); d.text((xx,cy),ln,font=font,fill="#FFB300",stroke_width=stroke,stroke_fill="#000000"); bboxes.append((xx,cy,xx+tw,cy+h)); cy+=h+round(fs*.15)
        union=(min(b[0] for b in bboxes),min(b[1] for b in bboxes),max(b[2] for b in bboxes),max(b[3] for b in bboxes)); passed=len(lines)<=2 and union[0]>=safe_x[0] and union[2]<=safe_x[1] and union[1]>=safe_y[0] and union[3]<=safe_y[1]; overall=overall and passed; out=output_dir/f"subtitle_preview_{label}.jpg"; frame.save(out,quality=92); records.append({"label":label,"path":str(out),"font_size":fs,"stroke":stroke,"lines":len(lines),"bbox":union,"safe_x":safe_x,"safe_y":safe_y,"anchor_y":anchor_y,"color":"#FFB300","result":"PASS" if passed else "FAIL"})
    return {"result":"PASS" if overall else "FAIL","previews":records}
