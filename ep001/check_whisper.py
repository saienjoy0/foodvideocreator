#!/usr/bin/env python3
"""分けた声を Whisper（faster-whisper, ランナーの CPU）で書き起こし、台本と比べる。Gemini の上限を使わない。→ ep001_out/check.json"""
import json, re, difflib, wave
import numpy as np
from pathlib import Path
from faster_whisper import WhisperModel
HERE = Path(__file__).parent
SCRIPT = json.loads((HERE / 'check' / 'script.json').read_text(encoding='utf-8'))
OUT = HERE.parent / 'ep001_out'; OUT.mkdir(exist_ok=True)
m = WhisperModel('medium', device='cpu', compute_type='int8')
norm = lambda s: re.sub(r'[\s、。，．,.？?！!「」『』（）()・…ー〜]', '', s)
res = {}
for lid, text in SCRIPT.items():
    p = HERE / 'check' / f'{lid}.wav'
    if not p.exists(): continue
    w = wave.open(str(p)); x = np.frombuffer(w.readframes(w.getnframes()), np.int16).astype(np.float32) / 32768
    segs, _ = m.transcribe(x, language='ja', beam_size=5)  # 台本を渡さない（引きずられないように）
    heard = ''.join(s.text for s in segs)
    ratio = difflib.SequenceMatcher(None, norm(text), norm(heard)).ratio()
    res[lid] = {'heard': heard, 'ratio': round(ratio, 3)}
    print(lid, round(ratio, 3), heard, flush=True)
(OUT / 'check.json').write_text(json.dumps(res, ensure_ascii=False, indent=1), encoding='utf-8')
