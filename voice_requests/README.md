# Voice requests

Adding a JSON file to this directory triggers `.github/workflows/gemini-tts.yml`.
The workflow reads the repository secret `GEMINI_API_KEY`, generates a WAV with Gemini TTS,
uploads it as a GitHub Actions artifact, then writes a small pointer JSON to `voice_results/<name>.json`.

Example:

```json
{
  "text": "この料理、見た目はただの白菜。でも正体は中国の高級料理。",
  "profile": {
    "voice_name": "Kore",
    "style": "自然な日本語。YouTube Shorts向けにテンポよく、聞き取りやすく。"
  }
}
```

`profile` is optional. Defaults are defined by the workflow/provider.
Do not put API keys in request files.
