import base64
import json
import os
import wave
from pathlib import Path
from google import genai
from google.genai import types

NAME = 'tic_oil_dumplings_20261109_tts_recovery'
OUT = Path('voice_outputs') / NAME
OUT.mkdir(parents=True, exist_ok=True)
REQUEST = json.loads(Path('voice_requests/tic_oil_dumplings_20261109_direct_recovery.json').read_text(encoding='utf-8'))
VOICE = REQUEST['profile']['voice_name']
STYLE = REQUEST['profile']['style']
TEXT = REQUEST['text']
client = genai.Client(api_key=os.environ['GEMINI_API_KEY'])

def get_audio(candidate):
    model, mode = candidate
    if mode == 'v38':
        response = client.interactions.create(
            model=model,
            input=[{'type': 'user_input', 'content': [{'type': 'text', 'text': TEXT, 'annotations': [{'type': 'speech_metadata', 'style': STYLE}]}]}],
            response_format={'type': 'audio'},
            generation_config={'speech_config': [{'voice': VOICE}]},
        )
        data = response.output_audio.data
        return base64.b64decode(data) if isinstance(data, str) else bytes(data), 'audio/wav'
    if mode == 'interactions':
        response = client.interactions.create(
            model=model, input=TEXT, response_format={'type': 'audio'},
            generation_config={'speech_config': [{'voice': VOICE}]},
        )
        data = response.output_audio.data
        return base64.b64decode(data) if isinstance(data, str) else bytes(data), 'audio/wav'
    prompt = (STYLE + '\n本文のみを一文字も変更せず読み上げてください。\n' + TEXT)
    response = client.models.generate_content(
        model=model,
        contents=prompt,
        config=types.GenerateContentConfig(
            response_modalities=['AUDIO'],
            speech_config=types.SpeechConfig(voice_config=types.VoiceConfig(prebuilt_voice_config=types.PrebuiltVoiceConfig(voice_name=VOICE))),
        ),
    )
    for part in response.candidates[0].content.parts:
        if part.inline_data and part.inline_data.data:
            data = part.inline_data.data
            b = base64.b64decode(data) if isinstance(data, str) else bytes(data)
            return b, part.inline_data.mime_type or 'audio/L16;rate=24000'
    raise ValueError('Gemini produced no audio data')

cases = [
    ('gemini-3.8-flash-lite-tts', 'v38'),
    ('gemini-3.1-flash-tts-preview', 'interactions'),
    ('gemini-2.5-flash-preview-tts', 'legacy'),
    ('gemini-2.5-pro-preview-tts', 'legacy'),
    ('gemini-2.5-flash-preview-tts', 'interactions'),
]
results = []
for model, mode in cases:
    try:
        audio, mime = get_audio((model, mode))
        if len(audio) < 1024:
            raise RuntimeError('audio shorter than 1KB')
        wavpath = OUT / 'voice.wav'
        if audio.startswith(b'RIFF') and audio[8:12] == b'WAVE':
            wavpath.write_bytes(audio)
        else:
            with wave.open(str(wavpath), 'wb') as wf:
                wf.setnchannels(1)
                wf.setsampwidth(2)
                wf.setframerate(24000)
                wf.writeframes(audio)
        with wave.open(str(wavpath), 'rb') as wf:
            dur = wf.getnframes() / wf.getframerate()
        results.append({'model': model, 'interface': mode, 'status': 'success', 'duration': dur})
        print('SUCCESS:', model, mode, f'{dur:.3f}s', flush=True)
        break
    except Exception as exc:
        error = f'{type(exc).__name__}: {str(exc)}'
        results.append({'model': model, 'interface': mode, 'status': 'error', 'error': error[:1000]})
        print('FAILED:', model, mode, error[:600], flush=True)
(OUT / 'diagnostics.json').write_text(json.dumps(results, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
if not any(x['status'] == 'success' for x in results):
    raise SystemExit(1)
