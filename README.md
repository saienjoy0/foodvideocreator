# foodvideocreator

中国グルメ YouTube Shorts 制作を、**人間承認ゲート付き・状態駆動・成果物SHA検証付き**で実行するMVP実装です。

設計正本: `docs/design_v1_6_2.md`

## 実装済み

- 17工程の `workflow/workflow_contract.yaml`
- SQLite状態管理 / `workflow_revision`
- 1案件につきOpen Gate最大1
- Presentation ID + Artifact SHAに結びつく承認
- Immutable versioned artifacts / project namespace
- `artifact_slots`: candidate / approved / change_pending
- MAIN_SOURCE変更時の新案件ロールオーバー
- Dish Identity 0.80 Hard Gate
- Story / Context Claim Evidence
- Script Lab構造Gate（3 Angle / 6–10 Hook / 2 Draft / 3 Critic / Pairwise / Beat Map / Hook-Payoff）
- 字幕密度 Draft / Tips / Final 三重QA
- Audio Policy / BGM Policy / Production Plan
- Voice actual duration gate / Alignment adapter
- ASS字幕生成・2行・安全bbox・事前3枚QA
- ffmpeg/ffprobe実動画レンダリング・全デコード・フレーム数/codec/解像度/fps QA
- A/B概要欄構造QAとClaim provenance
- BASE商品説明の確認済みフィールド provenance
- BASE商品画像 1024×1024 3役割
- 13A背景 QA + Mode A/B
- 13B `Noto Sans Mono CJK JP Bold` Full Name確認、5回重ね、bbox、0.55–1.00横圧縮、270×480 QA
- Final末尾0.1秒（fps由来整数フレーム）、黒末尾差し替え、映像本体/音声同一性QA
- EXTERNAL_RENDER正式ルート
- 各工程直前の現行v4 TXT全文Rule Bundleロード
- 外部AI / TTS / 画像生成のCommand Adapter
- Mock ProviderによるオフラインE2E回帰テスト

## 前提

- Python 3.11+
- `ffmpeg` / `ffprobe`
- 日本語Noto CJKフォント
- 13Bは **`Noto Sans Mono CJK JP Bold`** が実際のTTC Full Nameとして取得できること

Ubuntu/Debian系の例:

```bash
sudo apt-get install ffmpeg fonts-noto-cjk
```

Python:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e .
```

## 最初の検証

リポジトリルートで:

```bash
fvc validate
fvc validate --step THUMBNAIL_TEXT
pytest -q
```

`THUMBNAIL_TEXT` 検証ではTTC indexを推測せず、Full Name `Noto Sans Mono CJK JP Bold` を列挙して一致したfaceを使います。

## 基本操作

### 1. 案件作成

```bash
fvc --db jobs/demo/job.db --project demo init
```

### 2. 主動画登録

```bash
fvc --db jobs/demo/job.db --project demo import-asset MAIN_SOURCE /path/to/source.mp4
```

同じproject_idへ別SHAのMAIN_SOURCEを入れた場合、低層APIは上書きを拒否し、CLI/App境界で新しいproject_idへ自動ロールオーバーします。返却された新project_idを以後使います。

### 3. 制作開始

```bash
fvc --db jobs/demo/job.db --project demo user お願い --json '{"dish_name":"文思豆腐"}'
```

### 4. 承認

```bash
fvc --db jobs/demo/job.db --project demo user OK
```

`OK` は現在Open Gateだけを承認し、**次のユーザー可視工程を1つだけ**実行します。

### 5. 順位

```bash
fvc --db jobs/demo/job.db --project demo user '1と3'
```

### 6. Route

```bash
fvc ... user A
fvc ... user B
fvc ... user '誘導しなくていい'
```

### 7. BGM

```bash
fvc ... user 'BGMなし'
fvc ... user 'BGMあり'
fvc ... user ASMR
```

- `BGMなし` → NONE
- `BGMあり` → `assets/fixed_bgm.MP3`（元音声のおよそ1/2）
- `ASMR` → `asmr bgm.MP3` または `BGM_ASSET(kind=ASMR)`（元音声のおよそ1/5）

**ASMR音源はこのリポジトリには含まれていません。** 指定された場合は実Assetが来るまでHard Blockします。

## 外部完成動画

CapCut等ですでに動画が完成している場合:

```bash
fvc ... import-asset EXTERNAL_RENDER /path/to/completed.mp4
fvc ... run IMPORT_EXISTING_VIDEO
```

Machine QA → 必要Semantic QA → Video Gateを通し、Productionをやり直さずPublishingへ進めます。

## 実AI / TTS / 画像生成を接続する

MVPはベンダーに固定しません。

```bash
export FVC_AI_COMMAND='python examples/mock_ai_command.py'
export FVC_VOICE_COMMAND='python examples/mock_voice_command.py'
export FVC_IMAGE_COMMAND='python examples/mock_image_command.py'
```

本番では同じJSON protocolを実装した任意のコマンドへ置き換えます。
詳細: `docs/PROVIDER_PROTOCOL.md`

コマンド未指定時は**Mock Provider**です。Mockは回帰テスト用であり、本番Research/TTS/画像生成の代替ではありません。

## 中国語等の焼き込み字幕

09 Productionは承認済み元動画へ字幕/BGMを追加する工程で、料理を壊す可能性のある自動inpaintはしません。

- 字幕なし → PASS
- 焼き込み字幕あり → `SOURCE_PREPROCESS_REQUIRED`
- 除去が料理を壊す可能性 → `SOURCE_PREPROCESS_USER_DECISION_REQUIRED`
- 分析情報不足 → BLOCK

安全に前処理されたMAIN_SOURCEを入れ直す場合は新案件扱いになるため、前処理を制作開始前に行う運用を推奨します。

## v4 Rule Bundle

`rules/v4/` には現行TXTを正規化名で全文配置しています。各Activityは実行直前に対応Ruleを全文ロードし、そのSHAをProvider payload / fingerprintへ渡します。

旧単一 `13_Shortsサムネ` と13A/13Bの併存はStartup ValidationでFAILします。

## 安全性の要点

- 承認済みArtifactは上書きしない
- 新候補ができただけでは承認済みArtifactを変更しない
- Revision Requestは `change_pending=true` で下流を止める
- Gateは1件だけOpen
- Gateは表示したArtifact SHAへ固定
- Contractのblocking check FAIL時は次工程へ進まない
- MAIN_SOURCE以外の動画を09の加工元にしない
- 13A承認前に13B禁止
- 13Bで背景再生成禁止
- 未実測QAをPASSにしない
- API Key / Token / CookieはDB・Artifact・Logへ保存しない

## テスト

```bash
make test
```

主要E2E:

- A route → Final
- B route → BASE images → 13A → 13B → Final
- EXTERNAL_RENDER → Video approval
- Generated voice + fixed BGM
- final normal tail / black tail
- exact 13B font face
- project isolation / new MAIN_SOURCE rollover
- dish identity confirmation
- command orchestration (`OK`, rank, A/B)

検証結果は `E2E_REPORT.md` を参照してください。
