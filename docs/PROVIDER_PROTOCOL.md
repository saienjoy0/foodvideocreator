# Provider Command Protocol

`foodvideocreator` はAI/TTS/画像生成のベンダーを固定しない。
外部コマンドとは stdin/stdout JSON で通信する。

## AI Command

環境変数:

```bash
FVC_AI_COMMAND='python provider.py'
```

stdin:

```json
{
  "operation": "video_semantic_analysis",
  "payload": {}
}
```

stdoutはJSON object 1個だけを返す。ログはstderrへ出す。

### video_semantic_analysis

最低出力:

```json
{
  "dish_identity": "文思豆腐",
  "dish_identity_confidence": 0.95,
  "identity_basis": ["映像", "ユーザー指定"],
  "identity_conflict": false,
  "major_scenes": [{"start": 0, "end": 3, "description": "豆腐を細切り"}],
  "facts_visible": ["豆腐が非常に細く切られている"],
  "facts_unconfirmed": ["味", "歴史"],
  "audio": {"human_speech_present": true, "language": "zh", "asmr_present": true},
  "source_preprocess": {
    "burned_in_subtitle": false,
    "logo": false,
    "ui": false,
    "black_frame": false,
    "video_corruption": false,
    "subtitle_removal_risk": "PASS"
  }
}
```

`dish_identity_confidence < 0.80` または conflict=true ではResearchへ進めない。

### research_and_rank

各ClaimにEvidence必須。

```json
{
  "claims": [{
    "claim_id": "story_1",
    "claim_type": "STORY",
    "claim": "...",
    "classification": "history",
    "evidence_strength": "high",
    "sources": [{
      "source_id": "s1",
      "publisher": "...",
      "source_title": "...",
      "source_type": "official",
      "position": "supports",
      "evidence_summary": "...",
      "url": "https://...",
      "retrieved_at": "2026-08-17T00:00:00Z"
    }]
  }],
  "ranking": [{"rank": 1, "claim_id": "story_1", "point_name": "...", "why_interesting": "..."}]
}
```

classification:

```text
history | legend | folklore | general_characteristic | unverified
```

### script_lab

最低構造:

```json
{
  "angles": ["Gap", "Origin", "Problem/Solution"],
  "hooks": ["...", "...", "...", "...", "...", "..."],
  "drafts": [{"id": "a", "text": "..."}, {"id": "b", "text": "..."}],
  "critics": {
    "viewer": {"pass": true},
    "shorts_editor": {"pass": true},
    "fact": {"pass": true}
  },
  "pairwise_result": {"winner_id": "a", "reason": "..."},
  "rewrite_count": 1,
  "beat_map": [{"beat_id":"b1","start_sec":0,"end_sec":4,"claim_ids":["story_1"],"new_information":"...","narrative_role":"hook"}],
  "hook_payoff": {"status": "CLOSED", "payoff_claim_ids": ["story_1"]},
  "selected_text": "...",
  "tips_text": "...",
  "final_text": "...",
  "used_claim_ids": ["story_1", "context_1"]
}
```

`used_claim_ids` はSelection Confirmで承認されたStory/Context Claim集合のsubsetでなければFAIL。

### cta

```json
{"text":"...","policy":"NONE | LIKE_FOLLOW | BASE"}
```

CTA追加後も字幕密度範囲内であること。

### align_audio

```json
{
  "result": "PASS",
  "method": "forced_alignment",
  "cues": [{
    "speech_start": 1.2,
    "speech_end": 2.9,
    "start": 1.05,
    "end": 2.9,
    "text": "対応する承認済み字幕"
  }]
}
```

字幕開始は原則発話0.10–0.20秒前。

### publishing

```json
{
  "title": "...",
  "description": "...",
  "fact_check": {
    "used_claim_ids": ["story_1"],
    "new_fact_detected": false
  }
}
```

A/Bの文字数・行数・絵文字・ハッシュタグ・URLはコードで再検証する。

### base_copy

```json
{
  "product_name": "...",
  "description": "...",
  "internal_checks": ["賞味期限を出品前に確認"],
  "used_product_fields": ["product_name", "origin"],
  "unverified_product_fields": []
}
```

`used_product_fields` がユーザー提供 `product_info` の外へ出るとFAIL。

### semantic_video_qa

```json
{"result":"PASS","checks":{"script_meaning_match":true,"no_unapproved_addition":true,"dish_identity":true}}
```

### thumbnail_copy

入力payloadには `selection` と `approved_claims` が入り、Research全Claimは渡さない。

```json
{
  "line1":"...",
  "line2":"...",
  "line3":"...",
  "used_claim_ids":["story_1"],
  "new_fact_detected":false
}
```

### image_semantic_qa

13A例:

```json
{
  "result":"PASS",
  "text_zero":true,
  "logo_zero":true,
  "watermark_zero":true,
  "ui_zero":true,
  "no_mosaic":true,
  "no_black_band":true,
  "dish_large":true,
  "same_dish":true
}
```

270×480例では `small_readability=true` を含める。

## Voice Command

stdin:

```json
{
  "text": "読み上げ本文",
  "output_path": "/.../voice.wav",
  "profile": {"chars_per_second": 10.0}
}
```

コマンド自身が `output_path` に実音声ファイルを書き、stdout:

```json
{"duration": 5.8, "sample_rate": 24000}
```

Productionは生成後にffprobe等で実尺を再測定するため、申告値だけでPASSしない。

## Image Command

stdin:

```json
{
  "source_path":"/path/reference.jpg",
  "output_path":"/path/thumbnail_bg.jpg",
  "payload":{"no_text":true,"no_logo":true,"same_dish":true}
}
```

`output_path` に背景画像を作成し、stdout JSONを返す。
最終日本語文字はこのProviderへ描かせない。13BはPillowの実フォント合成だけで行う。
