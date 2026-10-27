#!/usr/bin/env python3
"""ep001 前編の声をまとめて作る（Gemini TTS）→ 実際の発話を聞いて行ごとの時刻を取る（Gemini 2.5 Flash）。
出力：out/<chunk>.wav、out/<chunk>.align.json、out/summary.json
まず全文を1回で頼み、短すぎる・失敗したときは章ごとに頼む。キーは GEMINI_API_KEY（Secrets）から。"""
from __future__ import annotations
import base64, json, os, sys, time, wave
from pathlib import Path

from google import genai
from google.genai import types

HERE = Path(__file__).parent
REQ = json.loads((HERE / 'voice_request.json').read_text(encoding='utf-8'))
OUT = HERE.parent / 'ep001_out'
OUT.mkdir(exist_ok=True)
KEYS = [k.strip() for k in (os.environ.get('GEMINI_API_KEYS') or os.environ.get('GEMINI_API_KEY', '')).splitlines() if k.strip()]
if not KEYS:
    sys.exit('GEMINI_API_KEY is missing')
CPS = 6.8  # 見積もりの読む速さ（字/秒）。短すぎる音声を見分けるのに使う


def log(*a):
    print(*a, flush=True)


def tts(text: str, path: Path) -> float:
    last = None
    for attempt in range(8):
        key = KEYS[attempt % len(KEYS)]
        try:
            client = genai.Client(api_key=key)
            it = client.interactions.create(
                model=REQ['model'],
                input=[{'type': 'user_input', 'content': [{'type': 'text', 'text': text, 'annotations': [{'type': 'speech_metadata', 'style': REQ['style']}]}]}],
                response_format={'type': 'audio'},
                generation_config={'speech_config': [{'voice': REQ['voice']}]},
            )
            data = it.output_audio.data
            audio = base64.b64decode(data) if isinstance(data, str) else bytes(data)
            if audio[:4] == b'RIFF':
                path.write_bytes(audio)
            else:
                with wave.open(str(path), 'wb') as w:
                    w.setnchannels(1); w.setsampwidth(2); w.setframerate(24000); w.writeframes(audio)
            with wave.open(str(path)) as w:
                return w.getnframes() / w.getframerate()
        except Exception as e:  # noqa
            last = e
            log(f'  tts retry {attempt + 1}: {type(e).__name__}: {str(e)[:200]}')
            time.sleep(min(60, 6 * (attempt + 1)))
    raise RuntimeError(f'TTS failed: {last}')


def align(lines: list[dict], path: Path) -> dict:
    numbered = '\n'.join(f"{i + 1}. {l['text']}" for i, l in enumerate(lines))
    prompt = (
        'この日本語音声を最初から最後まで実際に聞いてください。\n'
        f'以下の台本{len(lines)}文と、実際の発話を1文ずつ照合してください。文字数や無音だけから推測しないでください。\n'
        '各文について、発話開始秒 start と発話終了秒 end を0.01秒単位で返してください。\n'
        '本文の追加・省略・言い換え・読み間違いがあれば matched=false とし、heard に実際に聞こえた内容を書いてください。完全に同じなら matched=true。\n\n'
        f'台本:\n{numbered}\n\nJSONだけ返してください。形式:\n'
        '{"segments":[{"index":1,"matched":true,"heard":"...","start":0.00,"end":1.23}]}'
    )
    last = None
    for attempt in range(6):
        try:
            client = genai.Client(api_key=KEYS[attempt % len(KEYS)])
            resp = client.models.generate_content(
                model='gemini-2.5-flash',
                contents=[prompt, types.Part.from_bytes(data=path.read_bytes(), mime_type='audio/wav')],
                config=types.GenerateContentConfig(response_mime_type='application/json', temperature=0),
            )
            return json.loads((resp.text or '').strip())
        except Exception as e:  # noqa
            last = e
            log(f'  align retry {attempt + 1}: {type(e).__name__}: {str(e)[:200]}')
            time.sleep(8 * (attempt + 1))
    return {'error': str(last)}


def join(lines):
    return '\n\n'.join(l['text'] for l in lines)


summary = {'voice': REQ['voice'], 'model': REQ['model'], 'parts': []}
chunks = REQ['chunks']
all_lines = [l for c in chunks for l in c['lines']]
expected = sum(len(l['text']) for l in all_lines) / CPS
done = False
if REQ.get('try_whole_first'):
    p = OUT / 'whole.wav'
    try:
        log(f'whole: {len(all_lines)} lines, expect ~{expected:.0f}s')
        d = tts(join(all_lines), p)
        log(f'  whole -> {d:.1f}s')
        if d > expected * 0.75:
            if REQ.get('align', True):
                a = align(all_lines, p)
                (OUT / 'whole.align.json').write_text(json.dumps(a, ensure_ascii=False, indent=1), encoding='utf-8')
            summary['parts'].append({'id': 'whole', 'wav': 'whole.wav', 'dur': d, 'lines': [l['id'] for l in all_lines]})
            done = True
        else:
            log('  whole too short (cut off?) -> per chapter')
    except Exception as e:  # noqa
        log(f'  whole failed: {e} -> per chapter')
if not done:
    for c in chunks:
        p = OUT / f"{c['id']}.wav"
        exp = sum(len(l['text']) for l in c['lines']) / CPS
        log(f"{c['id']}: {len(c['lines'])} lines, expect ~{exp:.0f}s")
        d = tts(join(c['lines']), p)
        log(f'  -> {d:.1f}s')
        if REQ.get('align', True):
            a = align(c['lines'], p)
            (OUT / f"{c['id']}.align.json").write_text(json.dumps(a, ensure_ascii=False, indent=1), encoding='utf-8')
        summary['parts'].append({'id': c['id'], 'wav': p.name, 'dur': d, 'lines': [l['id'] for l in c['lines']]})
        time.sleep(3)
(OUT / 'summary.json').write_text(json.dumps(summary, ensure_ascii=False, indent=1), encoding='utf-8')
log('done', json.dumps(summary, ensure_ascii=False)[:500])
