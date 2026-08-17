from __future__ import annotations

import json
import math
import subprocess
from fractions import Fraction
from pathlib import Path
from typing import Any


def run(cmd: list[str], *, capture: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(cmd, text=True, capture_output=capture, check=True)


def ffprobe(path: str | Path) -> dict[str, Any]:
    proc = run(["ffprobe", "-v", "error", "-show_streams", "-show_format", "-of", "json", str(path)])
    data = json.loads(proc.stdout)
    v = next((s for s in data.get("streams", []) if s.get("codec_type") == "video"), None)
    a = next((s for s in data.get("streams", []) if s.get("codec_type") == "audio"), None)
    if not v:
        raise ValueError("VIDEO_STREAM_NOT_FOUND")
    fps_expr = v.get("avg_frame_rate") or v.get("r_frame_rate") or "0/1"
    fps = float(Fraction(fps_expr)) if fps_expr not in {"0/0", "N/A"} else 0.0
    duration = float(v.get("duration") or data.get("format", {}).get("duration") or 0.0)
    nb_frames = v.get("nb_frames")
    frame_count = int(nb_frames) if nb_frames and str(nb_frames).isdigit() else int(round(duration * fps)) if fps else 0
    return {
        "duration": duration,
        "fps": fps,
        "fps_expr": fps_expr,
        "frame_count": frame_count,
        "width": int(v.get("width") or 0),
        "height": int(v.get("height") or 0),
        "aspect_ratio": f"{v.get('width')}:{v.get('height')}",
        "video_codec": v.get("codec_name"),
        "audio_codec": a.get("codec_name") if a else None,
        "audio_present": a is not None,
        "sample_rate": int(a.get("sample_rate")) if a and a.get("sample_rate") else None,
        "format_name": data.get("format", {}).get("format_name"),
    }


def verify_decode(path: str | Path) -> dict[str, Any]:
    proc = subprocess.run(["ffmpeg", "-v", "error", "-i", str(path), "-f", "null", "-"], text=True, capture_output=True)
    return {"result": "PASS" if proc.returncode == 0 else "FAIL", "stderr": proc.stderr[-4000:]}


def extract_frame(video: str | Path, seconds: float, output: str | Path) -> Path:
    out = Path(output); out.parent.mkdir(parents=True, exist_ok=True)
    run(["ffmpeg", "-y", "-ss", f"{max(0, seconds):.3f}", "-i", str(video), "-frames:v", "1", "-q:v", "2", str(out)])
    return out


def extract_frame_number(video: str | Path, frame_number: int, output: str | Path) -> Path:
    out=Path(output); out.parent.mkdir(parents=True,exist_ok=True)
    run(["ffmpeg","-y","-i",str(video),"-vf",f"select=eq(n\\,{max(0,int(frame_number))})","-vsync","0","-frames:v","1","-q:v","2",str(out)])
    return out

def sample_frames(video: str | Path, output_dir: str | Path, points: list[float] | None = None) -> list[Path]:
    info = ffprobe(video)
    duration = info["duration"]
    points = points or [0.0, .25, .5, .75, .9, .95, max(0, 1 - .2 / duration) if duration else 1.0, 1.0]
    out = []
    frame_period=1.0/info["fps"] if info["fps"] else 0.05
    last_safe=max(0.0,duration-2*frame_period-0.001)
    for i, p in enumerate(points):
        if p == 1.0 and info.get("frame_count",0)>0:
            path=Path(output_dir)/f"frame_{i:02d}_final.jpg"
            out.append(extract_frame_number(video,info["frame_count"]-1,path))
            continue
        sec = p * duration if 0 <= p <= 1 else p
        sec=min(max(0.0,sec),last_safe)
        out.append(extract_frame(video, sec, Path(output_dir) / f"frame_{i:02d}_{sec:.3f}.jpg"))
    return out


def audio_duration(path: str | Path) -> float:
    proc = run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "default=noprint_wrappers=1:nokey=1", str(path)])
    return float(proc.stdout.strip())


def render_with_ass(source_video: str | Path, ass_path: str | Path, output_path: str | Path, *, voice_path: str | Path | None = None, bgm_path: str | Path | None = None, bgm_volume: float | None = None, preserve_original_audio: bool = True) -> Path:
    source_video = Path(source_video); output_path = Path(output_path); output_path.parent.mkdir(parents=True, exist_ok=True)
    inputs = ["-i", str(source_video)]
    if voice_path: inputs += ["-i", str(voice_path)]
    if bgm_path: inputs += ["-stream_loop", "-1", "-i", str(bgm_path)]
    filter_parts: list[str] = []
    mix_labels = []
    direct_audio_map = None
    if preserve_original_audio:
        mix_labels.append("[0:a]"); direct_audio_map = "0:a"
    input_idx = 1
    if voice_path:
        mix_labels.append(f"[{input_idx}:a]")
        if direct_audio_map is None: direct_audio_map = f"{input_idx}:a"
        input_idx += 1
    if bgm_path:
        vol = 0.5 if bgm_volume is None else bgm_volume
        filter_parts.append(f"[{input_idx}:a]volume={vol}[bgm]"); mix_labels.append("[bgm]")
        if direct_audio_map is None: direct_audio_map = "[bgm]"
    filter_parts.append(f"[0:v]ass='{str(ass_path).replace(':', '\\:')}'[v]")
    if len(mix_labels) > 1:
        filter_parts.append("".join(mix_labels) + f"amix=inputs={len(mix_labels)}:duration=first:dropout_transition=0[a]"); audio_map = "[a]"
    elif len(mix_labels) == 1:
        audio_map = direct_audio_map
    else:
        audio_map = None
    cmd = ["ffmpeg", "-y", *inputs, "-filter_complex", ";".join(filter_parts), "-map", "[v]"]
    if audio_map: cmd += ["-map", audio_map, "-c:a", "aac"]
    else: cmd += ["-an"]
    cmd += ["-c:v", "libx264", "-pix_fmt", "yuv420p", "-movflags", "+faststart", "-vsync", "0", str(output_path)]
    run(cmd)
    return output_path


def final_thumbnail_frames(fps: float) -> int:
    return max(1, round(fps * 0.1))


def detect_black_tail_start(path: str | Path, duration: float) -> float | None:
    proc = subprocess.run(["ffmpeg", "-v", "info", "-i", str(path), "-vf", "blackdetect=d=0.05:pix_th=0.02", "-an", "-f", "null", "-"], text=True, capture_output=True)
    import re
    segments=[]
    for m in re.finditer(r"black_start:([0-9.]+) black_end:([0-9.]+) black_duration:([0-9.]+)", proc.stderr):
        segments.append((float(m.group(1)), float(m.group(2))))
    for a,b in reversed(segments):
        if abs(b-duration) <= 0.12 or b >= duration-0.12: return a
    return None


def append_thumbnail(source_video: str | Path, thumbnail: str | Path, output: str | Path) -> dict[str, Any]:
    info = ffprobe(source_video); frames = final_thumbnail_frames(info["fps"]); dur = frames / info["fps"] if info["fps"] else 0.1
    output = Path(output); output.parent.mkdir(parents=True, exist_ok=True)
    black_start = detect_black_tail_start(source_video, info["duration"])
    if black_start is not None:
        cmd = ["ffmpeg", "-y", "-i", str(source_video), "-loop", "1", "-i", str(thumbnail), "-filter_complex", f"[1:v]scale={info['width']}:{info['height']}:force_original_aspect_ratio=increase,crop={info['width']}:{info['height']},setsar=1[thumb];[0:v][thumb]overlay=0:0:enable='gte(t,{black_start:.9f})'[v]", "-map", "[v]", "-map", "0:a?", "-t", f"{info['duration']:.9f}", "-c:v", "libx264", "-c:a", "copy", "-movflags", "+faststart", str(output)]
        run(cmd); mode="replace_black_tail"; display_duration=max(0.0, info["duration"]-black_start); display_frames=round(display_duration*info["fps"])
    else:
        cmd = ["ffmpeg", "-y", "-i", str(source_video), "-loop", "1", "-framerate", info["fps_expr"], "-t", f"{dur:.9f}", "-i", str(thumbnail), "-filter_complex", f"[1:v]scale={info['width']}:{info['height']}:force_original_aspect_ratio=increase,crop={info['width']}:{info['height']},setsar=1[thumb];[0:v][thumb]concat=n=2:v=1:a=0[v]", "-map", "[v]", "-map", "0:a?", "-c:v", "libx264", "-c:a", "copy", "-movflags", "+faststart", str(output)]
        run(cmd); mode="append_0_1s"; display_duration=dur; display_frames=frames
    return {"path": str(output), "mode":mode, "black_tail_start":black_start, "thumbnail_frames": display_frames, "thumbnail_duration": display_duration, "source_info": info, "output_info": ffprobe(output), "decode": verify_decode(output)}


def audio_content_md5(path: str | Path) -> str | None:
    info=ffprobe(path)
    if not info.get("audio_present"): return None
    proc=subprocess.run(["ffmpeg","-v","error","-i",str(path),"-map","0:a:0","-f","md5","-"], text=True,capture_output=True)
    if proc.returncode!=0: raise RuntimeError(f"AUDIO_MD5_FAILED:{proc.stderr[-1000:]}")
    line=proc.stdout.strip(); return line.split("=",1)[-1] if "=" in line else line


def compare_video_body(source_video: str | Path, final_video: str | Path, work_dir: str | Path, *, black_tail_start: float | None=None, threshold: float=10.0) -> dict[str, Any]:
    from PIL import Image, ImageChops, ImageStat
    source_info=ffprobe(source_video); duration=float(source_info["duration"]); body_end=duration
    if black_tail_start is not None: body_end=max(0.0,float(black_tail_start)-max(0.03,1.0/max(source_info.get("fps") or 30.0,1.0)))
    if body_end <= 0.08: return {"result":"PASS","reason":"no_comparable_body_before_allowed_tail","samples":[]}
    times=[]
    for f in [.2,.5,.8]:
        t=min(body_end*f, max(0.0,body_end-0.02))
        if t >= 0 and all(abs(t-x)>0.01 for x in times): times.append(t)
    work=Path(work_dir); work.mkdir(parents=True,exist_ok=True); samples=[]
    for i,t in enumerate(times):
        a=extract_frame(source_video,t,work/f"source_{i}.png"); b=extract_frame(final_video,t,work/f"final_{i}.png")
        ia=Image.open(a).convert("RGB"); ib=Image.open(b).convert("RGB")
        if ib.size!=ia.size: ib=ib.resize(ia.size)
        diff=ImageChops.difference(ia,ib); means=ImageStat.Stat(diff).mean; mad=sum(means)/len(means)
        samples.append({"time":t,"mean_abs_diff":mad,"result":"PASS" if mad<=threshold else "FAIL"})
    ok=all(s["result"]=="PASS" for s in samples)
    return {"result":"PASS" if ok else "FAIL","threshold":threshold,"body_end":body_end,"samples":samples}
