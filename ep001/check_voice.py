#!/usr/bin/env python3
"""分けた声を、10行ずつまとめて聞かせて台本と照らし合わせる（呼び出しを少なくする）。→ ep001_out/check.json
行と行のあいだに短いビープを入れて、Gemini に「n 番目の区間」で書き起こさせる。
429 のキーは 70 秒休ませて次のキーへ。モデルも順に試す。"""
import json, os, time
from pathlib import Path
from google import genai
from google.genai import types
HERE = Path(__file__).parent
SCRIPT = json.loads((HERE / 'check' / 'script.json').read_text(encoding='utf-8'))
KEYS = [k.strip() for k in (os.environ.get('GEMINI_API_KEYS') or os.environ.get('GEMINI_API_KEY', '')).splitlines() if k.strip()]
MODELS = ['gemini-2.5-flash', 'gemini-2.5-flash-lite', 'gemini-2.0-flash']
OUT = HERE.parent / 'ep001_out'; OUT.mkdir(exist_ok=True)
rest = {}  # key -> 休み終わりの時刻
print('keys', len(KEYS), flush=True)
groups = json.loads((HERE / 'check' / 'groups.json').read_text())
res = {}
call = 0
for g, grp in enumerate(groups):
    mp3 = HERE / 'check' / f'group{g}.mp3'
    numbered = '\n'.join(f'{i + 1}. {SCRIPT[l]}' for i, l in enumerate(grp))
    prompt = (f'この日本語音声は、ピー音で区切られた{len(grp)}個の区間です。1区間ずつ実際に聞いて書き起こし、同じ番号の台本と比べてください。'
              '言葉の追加・省略・語順の入れ替え・言い換え・読み間違いがあれば matched=false、句読点や漢字かな・数字の書き方の違いだけなら matched=true。'
              '区間の頭や終わりに、前後の文の切れ端が混ざっていれば extra に書いてください。\n'
              f'台本:\n{numbered}\n\nJSONだけ：{{"segments":[{{"index":1,"heard":"...","matched":true,"diff":"","extra":""}}]}}')
    data = mp3.read_bytes()
    got = None
    for attempt in range(40):
        now = time.time()
        live = [k for k in KEYS if rest.get(k, 0) <= now]
        if not live:
            w = min(rest.values()) - now + 1; print(f'  all keys resting, wait {w:.0f}s', flush=True); time.sleep(max(1, w)); continue
        k = live[call % len(live)]; m = MODELS[(attempt // max(1, len(KEYS))) % len(MODELS)]; call += 1
        try:
            r = genai.Client(api_key=k).models.generate_content(model=m, contents=[prompt, types.Part.from_bytes(data=data, mime_type='audio/mpeg')],
                                                                config=types.GenerateContentConfig(response_mime_type='application/json', temperature=0))
            got = json.loads(r.text); print(f'group {g}: ok ({m}, key #{KEYS.index(k) + 1})', flush=True); break
        except Exception as e:
            msg = str(e)
            if '429' in msg or 'RESOURCE_EXHAUSTED' in msg: rest[k] = time.time() + 70
            elif 'API_KEY_INVALID' in msg or 'PERMISSION_DENIED' in msg or '403' in msg: rest[k] = time.time() + 10 ** 9
            print(f'  group {g} retry ({m}, key #{KEYS.index(k) + 1}): {msg[:120]}', flush=True); time.sleep(2)
    if not got:
        for l in grp: res[l] = {'error': 'no answer'}
        continue
    for s in got.get('segments', []):
        i = s.get('index', 0) - 1
        if 0 <= i < len(grp): res[grp[i]] = s
    time.sleep(20)
(OUT / 'check.json').write_text(json.dumps(res, ensure_ascii=False, indent=1), encoding='utf-8')
for l in [x for grp in groups for x in grp]: print(l, res.get(l))
print('NG', [k for k, v in res.items() if not v.get('matched', False) or v.get('extra')])
