#!/usr/bin/env python3
from __future__ import annotations
import json, os, sys
from pathlib import Path


def fail(msg: str):
    print(msg, file=sys.stderr)
    raise SystemExit(2)

if len(sys.argv) != 3:
    fail('usage: gemini_align_voice.py <request.json> <voice.wav>')
req_path = Path(sys.argv[1])
wav_path = Path(sys.argv[2])
req = json.loads(req_path.read_text(encoding='utf-8'))
segments = req.get('segments')
if not isinstance(segments, list) or not segments:
    fail('segments required')
if not wav_path.is_file():
    fail(f'voice file not found: {wav_path}')
api_key = os.environ.get('GEMINI_API_KEY','').strip()
if not api_key:
    fail('GEMINI_API_KEY is not set')
from google import genai
from google.genai import types
client = genai.Client(api_key=api_key)
numbered = '\n'.join(f"{i+1}. {s}" for i,s in enumerate(segments))
prompt = f'''この日本語音声を最初から最後まで実際に聞いてください。\n以下の確定字幕7文と、実際に発話されている内容を1文ずつ照合してください。文字数や無音区間だけから推測しないでください。\n各文について、実際の発話開始秒 start、発話終了秒 end を0.01秒単位で返してください。\nGemini TTSが本文を追加・省略・言い換えしていた場合は matched=false とし、heard に実際に聞こえた内容を書いてください。完全に同じなら matched=true。\n字幕は発話開始0.10〜0.20秒前に出すので、発話そのものの時刻だけを返してください。\n\n確定字幕:\n{numbered}\n\nJSONだけ返してください。形式:\n{{"audio_verified":true,"segments":[{{"index":1,"text":"...","matched":true,"heard":"...","start":0.00,"end":1.23}}]}}'''
audio = types.Part.from_bytes(data=wav_path.read_bytes(), mime_type='audio/wav')
resp = client.models.generate_content(
    model='gemini-2.5-flash',
    contents=[prompt, audio],
    config=types.GenerateContentConfig(response_mime_type='application/json', temperature=0),
)
text = (resp.text or '').strip()
try:
    parsed = json.loads(text)
except Exception:
    fail('Gemini alignment did not return valid JSON: ' + text[:1000])
print(json.dumps(parsed, ensure_ascii=False, indent=2))
