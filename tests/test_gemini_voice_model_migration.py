import base64
import importlib.util
import io
import json
import os
import sys
import tempfile
import types
import unittest
import wave
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch


PROVIDER_PATH = Path(__file__).resolve().parents[1] / "examples" / "gemini_voice_command.py"
spec = importlib.util.spec_from_file_location("gemini_voice_command", PROVIDER_PATH)
provider = importlib.util.module_from_spec(spec)
spec.loader.exec_module(provider)


class GeminiVoiceModelMigrationTest(unittest.TestCase):
    def test_new_models_keep_style_out_of_spoken_text_and_save_wav(self):
        pcm = b"\x00\x00" * 240
        buffer = io.BytesIO()
        with wave.open(buffer, "wb") as wav:
            wav.setnchannels(1)
            wav.setsampwidth(2)
            wav.setframerate(24000)
            wav.writeframes(pcm)
        recorded = []

        class Interactions:
            def create(self, **kwargs):
                recorded.append(kwargs)
                return types.SimpleNamespace(output_audio=types.SimpleNamespace(
                    data=base64.b64encode(buffer.getvalue()).decode()
                ))

        class FakeClient:
            def __init__(self, api_key):
                self.interactions = Interactions()

        google = types.ModuleType("google")
        google.genai = types.ModuleType("google.genai")
        google.genai.Client = FakeClient
        google.genai.types = types.SimpleNamespace()

        for model in ("gemini-3.8-flash-tts", "gemini-3.8-flash-lite-tts"):
            with self.subTest(model=model), tempfile.TemporaryDirectory() as tmp:
                output = Path(tmp) / "voice.wav"
                request = {"text": "この料理はおいしい。", "output_path": str(output),
                           "profile": {"model": model, "voice_name": "Fenrir", "style": "熱血漢"}}
                stdout = io.StringIO()
                with patch.dict(os.environ, {"GEMINI_API_KEY": "test-key"}), \
                     patch.dict(sys.modules, {"google": google, "google.genai": google.genai}), \
                     patch.object(sys, "stdin", io.StringIO(json.dumps(request))), redirect_stdout(stdout):
                    provider.main()

                call = recorded[-1]
                part = call["input"][0]["content"][0]
                self.assertEqual(part["text"], request["text"])
                self.assertEqual(part["annotations"][0]["style"], "熱血漢")
                self.assertEqual(call["generation_config"]["speech_config"], [{"voice": "Fenrir"}])
                with wave.open(str(output), "rb") as wav:
                    self.assertEqual(wav.getframerate(), 24000)
                self.assertEqual(json.loads(stdout.getvalue())["model"], model)


if __name__ == "__main__":
    unittest.main()
