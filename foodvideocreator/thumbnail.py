from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw, ImageEnhance, ImageFont

from .fonts import TARGET_FULL_NAME, find_font_face

SAFE_X = (162, 918); SAFE_Y = (480, 1440); PSEUDO = [(-2,0),(2,0),(0,-2),(0,2),(0,0)]; COLORS = ["#FFFFFF", "#FF1608", "#FFE900"]; START_SIZES = [150, 285, 245]; STROKES = [30, 42, 40]; CENTERS_Y = [580, 850, 1180]

def _font(path: Path, index: int | None, size: int): return ImageFont.truetype(str(path), size=size, index=0 if index is None else index)

def crop_cover(im: Image.Image, size=(1080,1920)) -> Image.Image:
    tw, th = size; w, h = im.size; scale = max(tw/w, th/h); nw, nh = round(w*scale), round(h*scale); im = im.resize((nw,nh), Image.Resampling.LANCZOS); left=(nw-tw)//2; top=(nh-th)//2; return im.crop((left,top,left+tw,top+th))

def make_background_mode_a(source: str | Path, output: str | Path, *, brightness=1.02, contrast=1.04, saturation=1.04, sharpness=1.05) -> dict[str, Any]:
    im = Image.open(source).convert("RGB"); im = crop_cover(im); im = ImageEnhance.Brightness(im).enhance(brightness); im = ImageEnhance.Contrast(im).enhance(contrast); im = ImageEnhance.Color(im).enhance(saturation); im = ImageEnhance.Sharpness(im).enhance(sharpness); out=Path(output); out.parent.mkdir(parents=True, exist_ok=True); im.save(out, quality=95); return {"mode":"A","canvas":"1080x1920","path":str(out),"sha256":hashlib.sha256(out.read_bytes()).hexdigest()}

def _render_text_layer(text: str, font_path: Path, face_index: int|None, font_size: int, stroke: int, color: str, target_width: int = 740) -> tuple[Image.Image, float, tuple[int,int,int,int]]:
    font = _font(font_path, face_index, font_size); pad = stroke + 16; probe = Image.new("RGBA", (2400, 800), (0,0,0,0)); d=ImageDraw.Draw(probe); bbox=d.textbbox((pad,pad), text, font=font, stroke_width=stroke); w=bbox[2]-bbox[0]+pad*2; h=bbox[3]-bbox[1]+pad*2; layer=Image.new("RGBA", (max(1,w+16),max(1,h+16)), (0,0,0,0)); dl=ImageDraw.Draw(layer); origin=(pad-bbox[0], pad-bbox[1])
    for dx,dy in PSEUDO: dl.text((origin[0]+dx+6, origin[1]+dy+7), text, font=font, fill="#000000", stroke_width=stroke, stroke_fill="#000000")
    for dx,dy in PSEUDO: dl.text((origin[0]+dx, origin[1]+dy), text, font=font, fill=color, stroke_width=stroke, stroke_fill="#000000")
    alpha=layer.getchannel("A"); bb=alpha.getbbox() or (0,0,layer.width,layer.height); layer=layer.crop(bb); scale=min(1.0, target_width/layer.width)
    if scale < .55: scale=.55
    if scale < 1: layer=layer.resize((round(layer.width*scale), layer.height), Image.Resampling.LANCZOS)
    return layer, scale, (0,0,layer.width,layer.height)

def compose_thumbnail_text(background: str | Path, lines: list[str], output: str | Path, preview: str | Path | None = None) -> dict[str, Any]:
    if len(lines)!=3: raise ValueError("THUMBNAIL_COPY_REQUIRES_3_LINES")
    font_path, face_index=find_font_face(); bg=Image.open(background).convert("RGBA")
    if bg.size!=(1080,1920): raise ValueError("BACKGROUND_MUST_BE_1080x1920")
    canvas=bg.copy(); records=[]
    for i,(text,size,stroke,color,cy) in enumerate(zip(lines,START_SIZES,STROKES,COLORS,CENTERS_Y),1):
        cur_size=size
        while True:
            layer,scale,_=_render_text_layer(text,font_path,face_index,cur_size,stroke,color)
            if layer.width <= SAFE_X[1]-SAFE_X[0]: break
            cur_size-=4
            if cur_size < 80: raise RuntimeError(f"THUMBNAIL_TEXT_CANNOT_FIT_LINE{i}")
        x=round((1080-layer.width)/2); y=round(cy-layer.height/2); x=max(SAFE_X[0],min(x,SAFE_X[1]-layer.width)); y=max(SAFE_Y[0],min(y,SAFE_Y[1]-layer.height)); bbox=(x,y,x+layer.width,y+layer.height)
        if bbox[0] < SAFE_X[0] or bbox[2] > SAFE_X[1] or bbox[1] < SAFE_Y[0] or bbox[3] > SAFE_Y[1]: raise RuntimeError(f"THUMBNAIL_BBOX_FAIL_LINE{i}:{bbox}")
        canvas.alpha_composite(layer,(x,y)); records.append({"line":i,"font_size":cur_size,"stroke":stroke,"horizontal_scale":round(scale,4),"bbox":bbox})
    out=Path(output); out.parent.mkdir(parents=True, exist_ok=True); canvas.convert("RGB").save(out, quality=95); pv=Path(preview) if preview else out.with_name(out.stem+"_270x480.jpg"); canvas.convert("RGB").resize((270,480),Image.Resampling.LANCZOS).save(pv,quality=95); sha=hashlib.sha256(out.read_bytes()).hexdigest()
    return {"font_name":TARGET_FULL_NAME,"font_path":str(font_path),"font_collection_index":face_index,"canvas":"1080x1920","lines":records,"small_preview":str(pv),"small_readability":"PENDING","real_font_composite":True,"thumbnail_sha256":sha,"output":str(out)}
