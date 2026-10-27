#!/usr/bin/env python3
"""ep001/check/<行id>.mp3 を1本ずつ聞いて書き起こし、台本と一致するか確かめる → ep001_out/check.json"""
import json, os, time
from pathlib import Path
from google import genai
from google.genai import types
HERE = Path(__file__).parent
SCRIPT = json.loads((HERE / 'check' / 'script.json').read_text(encoding='utf-8'))
KEYS = [k.strip() for k in (os.environ.get('GEMINI_API_KEYS') or os.environ.get('GEMINI_API_KEY', '')).splitlines() if k.strip()]
OUT = HERE.parent / 'ep001_out'; OUT.mkdir(exist_ok=True)
res = {}
dead = set()
def key(i):
    live = [k for k in KEYS if k not in dead] or KEYS
    return live[i % len(live)]
for i, (lid, text) in enumerate(SCRIPT.items()):
    p = HERE / 'check' / f'{lid}.mp3'
    if not p.exists(): res[lid] = {'error': 'no file'}; continue
    prompt = ('この日本語の音声を聞いて、聞こえたとおりに書き起こしてください。そのうえで、次の台本と比べて、'
              '言葉の追加・省略・語順の入れ替え・言い換え・読み間違いがあれば matched=false、句読点や漢字かなの違いだけなら matched=true にしてください。'
              '前後に別の文が混ざっていれば extra に書いてください。\n'
              f'台本：{text}\nJSONだけ：{{"heard":"...","matched":true,"diff":"違いの説明（なければ空）","extra":""}}')
    for a in range(12):
        try:
            k = key(i + a); c = genai.Client(api_key=k)
            r = c.models.generate_content(model='gemini-2.5-flash', contents=[prompt, types.Part.from_bytes(data=p.read_bytes(), mime_type='audio/mpeg')],
                                          config=types.GenerateContentConfig(response_mime_type='application/json', temperature=0))
            res[lid] = json.loads(r.text); break
        except Exception as e:
            msg = str(e)
            if any(x in msg for x in ('429', 'RESOURCE_EXHAUSTED', 'quota', 'API_KEY_INVALID', 'PERMISSION_DENIED')): dead.add(k)
            print('retry', lid, msg[:150], 'keys left', len(KEYS) - len(dead), flush=True); time.sleep(3 + 2 * a)
    print(lid, res.get(lid), flush=True)
(OUT / 'check.json').write_text(json.dumps(res, ensure_ascii=False, indent=1), encoding='utf-8')
bad = [k for k, v in res.items() if not v.get('matched', False) or v.get('extra')]
print('NG', bad)
