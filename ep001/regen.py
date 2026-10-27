#!/usr/bin/env python3
"""読み違えた行だけを1行ずつ作り直す。作るたびに Whisper で聞き、禁止の言い回しが出ず、台本との一致が十分なものだけ採る。→ ep001_out/regen/<id>.wav"""
import base64, json, os, re, time, wave, difflib, io
from pathlib import Path
import numpy as np
from google import genai
from faster_whisper import WhisperModel
HERE = Path(__file__).parent
R = json.loads((HERE / 'regen.json').read_text(encoding='utf-8'))
KEYS = [k.strip() for k in (os.environ.get('GEMINI_API_KEYS') or os.environ.get('GEMINI_API_KEY', '')).splitlines() if k.strip()]
OUT = HERE.parent / 'ep001_out' / 'regen'; OUT.mkdir(parents=True, exist_ok=True)
asr = WhisperModel('medium', device='cpu', compute_type='int8')
norm = lambda s: re.sub(r'[\s、。，．,.？?！!「」『』（）()・…ー〜]', '', s)
def tts(text):
    for a in range(10):
        try:
            c = genai.Client(api_key=KEYS[a % len(KEYS)])
            it = c.interactions.create(model=R['model'], input=[{'type': 'user_input', 'content': [{'type': 'text', 'text': text, 'annotations': [{'type': 'speech_metadata', 'style': R['style'] + ' 書かれた文を一字一句そのまま読む。語尾を「です・ます」に変えない。語順を変えない。'}]}]}],
                                     response_format={'type': 'audio'}, generation_config={'speech_config': [{'voice': R['voice']}]})
            d = it.output_audio.data; b = base64.b64decode(d) if isinstance(d, str) else bytes(d)
            return b
        except Exception as e:
            print('  tts retry', a, str(e)[:160], flush=True); time.sleep(20 + 10 * a)
    return None
def to_wav(b, path):
    if b[:4] == b'RIFF': path.write_bytes(b)
    else:
        with wave.open(str(path), 'wb') as w: w.setnchannels(1); w.setsampwidth(2); w.setframerate(24000); w.writeframes(b)
report = {}
for L in R['lines']:
    best = None
    for take in range(4):
        b = tts(L['text'])
        if not b: break
        p = OUT / f"{L['id']}_t{take}.wav"; to_wav(b, p)
        w = wave.open(str(p)); x = np.frombuffer(w.readframes(w.getnframes()), np.int16).astype(np.float32) / 32768; sr = w.getframerate()
        x16 = np.interp(np.arange(int(len(x) * 16000 / sr)) * sr / 16000, np.arange(len(x)), x).astype(np.float32)
        heard = ''.join(s.text for s in asr.transcribe(x16, language='ja', beam_size=5)[0])
        ratio = difflib.SequenceMatcher(None, norm(L['text']), norm(heard)).ratio()
        bad = [f for f in L['forbid'] if f in heard] + ['need:' + n for n in L.get('need', []) if n not in heard]
        print(L['id'], 'take', take, round(ratio, 3), bad, heard, flush=True)
        if not bad and (best is None or ratio > best[1]): best = (p, ratio, heard)
        if not bad and ratio >= 0.9: break
        time.sleep(8)
    if best:
        (OUT / f"{L['id']}.wav").write_bytes(best[0].read_bytes())
        report[L['id']] = {'ok': True, 'ratio': round(best[1], 3), 'heard': best[2]}
    else:
        report[L['id']] = {'ok': False}
    time.sleep(6)
(OUT / 'report.json').write_text(json.dumps(report, ensure_ascii=False, indent=1), encoding='utf-8')
print('report', json.dumps(report, ensure_ascii=False))
