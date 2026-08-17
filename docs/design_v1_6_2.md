# 中国グルメ YouTube Shorts 制作システム 実装設計書 v1.6.2
## Final MVP Implementation Contract

> **STATUS: IMPLEMENTATION CANDIDATE**
> v1.6.1を基礎に、実装前レビューで残った5点だけを閉じたMVP正本候補。

# 0. v1.6.2で追加・修正する点

1. 全ユーザー可視工程を `workflow/workflow_contract.yaml` に完全列挙する。
2. Dish Identity Hard Gateを復活する。
3. Claim Evidence構造を復活する。
4. `EXTERNAL_RENDER` の正式Workflowを追加する。
5. `artifact_slots` テーブルを追加し、candidate / approved / change_pending を保存する。

v1.6.1で確定した以下は変更しない。

- 1回答 = 1ユーザー可視工程
- Open Gate最大1
- Approvalは表示Artifact SHAへ結びつける
- Data Dependency / Control Requirementを分離
- Immutable Artifact
- Draft / Tips / Finalの字幕密度三重Gate
- Script Lab
- BGM / A-B / 採用順位はユーザー決定
- 13A → OK → 13B → OK → Final
- SQLite中心のMVP
- 完全Event SourcingはMVP必須にしない

# 1. ユーザー指示の優先順位

```text
最新ユーザー指示
>
修正後に承認された成果物
>
既存承認済み成果物
>
現行Rule
>
旧Rule
>
過去AI提案
```

Directiveへ保存すべき代表例：

```text
DENSITY_OVERRIDE
LANGUAGE_STYLE
CTA_POLICY
ROUTE
BGM_POLICY
AUDIO_POLICY
TRANSLATION_POLICY
SUBTITLE_TEXT_LOCK
THUMBNAIL_COPY_LOCK
SOURCE_PRESERVATION
```

# 2. Dish Identity Hard Gate

Video Analysis Artifactには最低限：

```json
{
  "dish_identity": "",
  "dish_identity_confidence": 0.0,
  "identity_basis": [],
  "identity_conflict": false
}
```

Researchへ進める条件：

```text
dish_identity_confidence >= 0.80
AND
identity_conflict = false
```

未達：

```text
CHECK_DISH_IDENTITY = NEEDS_USER_CONFIRMATION
```

Research禁止。

ユーザー確認後はAnalysisを上書きせず、新versionを作る。

# 3. Claim Evidence

Story Claims / Context Claimsの双方へEvidenceを持たせる。

```json
{
  "claim_id": "claim_001",
  "claim_type": "STORY | CONTEXT",
  "claim": "",
  "classification": "history | legend | folklore | general_characteristic | unverified",
  "evidence_strength": "high | medium | low",
  "sources": [
    {
      "source_id": "",
      "publisher": "",
      "source_title": "",
      "source_type": "official | academic | museum | media | reference | other",
      "position": "supports | contradicts | uncertain",
      "evidence_summary": "",
      "url": "",
      "retrieved_at": ""
    }
  ]
}
```

Fact Criticはこの構造を根拠にする。

# 4. Artifact Slots

SQLiteへ追加：

```text
artifact_slots
--------------------------------
project_id
slot
current_candidate_id
current_approved_id
change_pending
updated_at
```

ルール：

```text
Artifact生成
→ current_candidate_id を更新可能
→ current_approved_id は変更禁止
```

Approval：

```text
GATE APPROVE
→ current_approved_id = gate.artifact_id
→ change_pending = false
```

Revision Request：

```text
REQUEST_REVISION
→ change_pending = true
→ 現GateをCLOSE
→ current_approved_idは履歴として保持
→ 下流Control Requirementでは承認無効扱い
```

その後：

```text
修正Activity
→ 新Artifact生成
→ current_candidate_id = new artifact
→ 新Gate OPEN
```

修正依頼時点で存在しない新versionをcandidateへ設定してはならない。

# 5. External Render

Asset Role：

```text
MAIN_SOURCE
EXTERNAL_RENDER
REFERENCE_VIDEO
REFERENCE_IMAGE
PRODUCT_IMAGE
VOICE_ASSET
BGM_ASSET
OTHER_ASSET
```

新案件になるのは：

```text
role=MAIN_SOURCE
AND
current MAIN_SOURCE SHAと異なる
```

時だけ。

ユーザーが「もう動画完成」「概要欄とサムネだけ」と明示した場合：

```text
EXTERNAL_RENDER
↓
IMPORT_EXISTING_VIDEO
↓
Machine QA
↓
必要なSemantic QA
↓
VIDEO_CANDIDATE
↓
WAITING_VIDEO_APPROVAL
↓ USER OK
VIDEO_APPROVED
↓
Publishing
```

Productionを再実行しない。

# 6. Source Preprocess Check

Production前に最低限：

```text
burned_in_subtitle
logo
UI
black_frame
video_corruption
audio_present
```

中国語等の焼き込み字幕：

```text
なし
→ PASS

安全に除去可能
→ PREPROCESS

料理を壊す可能性
→ USER_DECISION_REQUIRED
```

元料理を生成AIで勝手に描き直して字幕を消さない。

# 7. 13A / 13B測定保存

13A Artifact metadata：

```text
mode=A|B
source_sha256
output_sha256
canvas=1080x1920
```

13BのCheck.measurementへ必ず保存：

```text
font_full_name
font_size_line1/2/3
stroke_line1/2/3
horizontal_scale_line1/2/3
bbox_line1/2/3
canvas
small_readability
real_font_composite
thumbnail_sha256
```

# 8. Workflow Contract

`workflow/workflow_contract.yaml` をWorkflow Engineの工程定義正本とする。

各Step必須キー：

```text
step_id
user_visible
data_dependencies
control_requirements
required_directives
outputs
blocking_checks
opens_gate
next_step
```

正式Step：

```text
VIDEO_ANALYSIS
RESEARCH_RANKING
SELECTION_CONFIRM
SCRIPT_DRAFT
TIPS
ROUTE_SELECTION
CTA
SCRIPT_FINAL
PRODUCTION
IMPORT_EXISTING_VIDEO
PUBLISHING_A
PUBLISHING_B
BASE_COPY
BASE_IMAGES
THUMBNAIL_BG
THUMBNAIL_TEXT
FINAL
```

# 9. Workflow Contract Validation

起動時に：

```text
全正式Step存在
必須キー存在
参照Step存在
Gate名重複なし
Output名空欄なし
```

を検証する。

FAILなら案件開始禁止。

# 10. Regression Tests

最低限：

```text
Dish Identity confidence 0.79
→ Research禁止
```

```text
Dish Identity confidence 0.80 / conflict=false
→ Research可能
```

```text
Approved A
↓ Candidate B生成
→ Approved Aは維持
```

```text
Approved A
↓ REQUEST_REVISION
→ change_pending=true
→ downstream禁止
```

```text
REQUEST_REVISION直後
→ 存在しない新candidateを設定しない
```

```text
EXTERNAL_RENDER
→ 新Projectを作らない
→ Import Existing Videoへ
```

```text
MAIN_SOURCE SHA変更
→ 新Project
```

```text
Open Gate 2つ
→ FAIL
```

```text
表示Artifact A
↓ Candidate B生成
↓ AのPresentationに対してOK
→ Bを承認しない
```

```text
Draft PASS
↓ Tips FAIL
→ Route禁止
```

```text
Tips PASS
↓ Final FAIL
→ Script Lock禁止
```

# 11. MVP技術構成

```text
Python
SQLite
JSON / YAML-compatible workflow contract
ffmpeg / ffprobe
pytest
AI API Adapter
```

MVPではTemporal / Argo / Dagster / 完全Event Sourcingを実装しない。

# 12. 実装開始範囲

最初の実装対象：

```text
workflow_contract.yaml
SQLite schema
Workflow Contract Validator
Workflow State
Artifact Registry
Artifact Slots
Gate（Open最大1）
Approval Binding
Dish Identity Gate
Density Counter
Regression Tests
```

これがPASSしてからAI API・動画処理を接続する。

# 13. CANONICAL昇格

このv1.6.2のContractとPhase 1実装がテストPASSした時点で、
大きな設計変更を止め、実案件E2Eから得た失敗だけをRegression Testへ追加する。

## End of Design v1.6.2
