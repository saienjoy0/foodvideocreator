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

New requests use `gemini-3.8-flash-tts` by default. For faster, lower-cost
generation, set `"model": "gemini-3.8-flash-lite-tts"` inside `profile`.
Both models offer a free tier for standard API requests, subject to account
limits. Keep delivery instructions in `profile.style`; Gemini 3.8 receives
the `text` field verbatim and the style separately as speech metadata.
Existing request JSON files with an explicit older model keep that setting.

Choose the voice and delivery independently for every new video. After agreeing
on the sound for that video, put its `voice_name` and `style` in that video's
request JSON. The workflow defaults are only fallbacks; they do not lock all
videos to Kore, Fenrir, or any one narration style. For example:

```json
{
  "text": "読み上げる本文をここに入れる。",
  "profile": {
    "model": "gemini-3.8-flash-lite-tts",
    "voice_name": "Fenrir",
    "style": "成人男性。勢いよく、語尾は明瞭に。叫びすぎない。"
  }
}
```
