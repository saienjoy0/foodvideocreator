# Implementation Status — v1.6.2 Complete MVP

Status: **IMPLEMENTED / VERIFIED WITH MOCK & COMMAND ADAPTERS**

## Workflow core

- 17/17 formal workflow steps implemented
- `workflow_contract.yaml` is validated at startup
- SQLite workflow state + separate `workflow_revision` / audit sequence
- Data dependencies and control requirements enforced by the engine
- immutable, versioned, project-namespaced artifacts
- artifact SHA verification / dependency freshness
- `artifact_slots`: current candidate / current approved / change pending
- one-open-user-gate invariant
- Presentation ID + artifact SHA bound approvals
- revision request does not fabricate a future candidate
- new MAIN_SOURCE rolls over to a new project at the application boundary
- EXTERNAL_RENDER stays in the current project

## AI / evidence / script

- Dish Identity 0.80 hard gate + conflict gate
- Story Claims / Context Claims
- evidence classification: history / legend / folklore / general characteristic / unverified
- evidence structural validation
- ranking selection hard gate
- only approved Selection Confirm claims are exposed to Script/Publishing/generated thumbnail copy
- Script Lab structure hard gate:
  - 3+ angles
  - 6–10 hooks
  - 2+ drafts
  - Viewer / Shorts Editor / Fact critics
  - pairwise result
  - max 1 rewrite
  - Beat Map
  - closed Hook-Payoff
- Draft / Tips / Final effective-character density gates
- display text / spoken text separation via `PRONUNCIATION_MAP`
- Script Final lock by approved SHA

## Production

- source ffprobe + full decode analysis
- source preprocess completeness hard gate
- burned-in subtitle / destructive-removal guard
- audio policy modes
- BGM NONE / FIXED / ASMR policy
- repository `fixed_bgm.MP3` can be used globally
- missing ASMR asset blocks rather than substitutes
- generated voice duration measured from the actual file
- voice artifact fingerprint reuse
- external alignment adapter
- subtitle cue timing validation
- same layout algorithm used by preview and final ASS
- max 2 lines / safe bbox / #FFB300 / thick stroke
- three design previews before render
- render from MAIN_SOURCE only
- H.264/AAC/fps/resolution/frame-count/full-decode checks
- semantic video QA adapter

## Publishing / BASE

- A/B publishing format QA
- URL once on B route
- CTA-none rule on A route
- approved-claim provenance for publishing facts
- confirmed-product-field provenance for BASE copy
- 1024×1024 BASE images, 3 distinct roles
- product-image asset gate

## Thumbnail / Final

- 13A and 13B physically separate through user gate
- 13A 1080×1920 and semantic background QA
- Mode A deterministic / Mode B image-provider adapter
- no final text is sent to image-generation provider
- 13B exact Full Name `Noto Sans Mono CJK JP Bold`
- TTC face enumerated; no guessed index
- five-pass pseudo weight
- 150/285/245 start sizes
- 30/42/40 strokes
- horizontal-only scale 0.55–1.00
- safe bbox X162–918 / Y480–1440
- real 270×480 preview + semantic readability QA
- all required 13B measurements stored in manifest
- final uses only approved video + approved 13B SHA
- 0.1 sec converted to integer frames from real fps
- black tail replaced instead of appending behind it
- final body comparison and decoded-audio MD5 equality

## Provider adapters

- AI JSON command adapter
- Voice command adapter
- Image command adapter
- deterministic Mock providers for offline regression
- provider protocol documented in `docs/PROVIDER_PROTOCOL.md`

No live third-party AI/TTS/image service is hard-coded. Production integration is done by supplying commands through `FVC_AI_COMMAND`, `FVC_VOICE_COMMAND`, and `FVC_IMAGE_COMMAND`.

## Verification

- Workflow contract: 17/17
- Current v4 rule files: 19/19
- `ffmpeg`: PASS
- `ffprobe`: PASS
- exact thumbnail font face: PASS; observed TTC index 5 in this environment
- Command AI/TTS/Image process boundaries: PASS
- Route A full Final E2E: PASS
- Route B through BASE → 13A → 13B → Final: PASS
- External Render: PASS
- generated voice + fixed BGM: PASS
- normal-tail and black-tail Final QA: PASS
- project isolation / new-main-source rollover: PASS
- latest full pytest run: **53 passed**

## Intentional external requirements

1. **Real research / semantic AI**: connect an external provider command. Mock is test-only.
2. **Real TTS**: connect a voice command. Mock produces a deterministic WAV for testing.
3. **13A Mode B real image generation**: connect an image command. Mock is test-only.
4. **ASMR BGM**: not supplied. `ASMR` correctly blocks until an actual ASMR asset is provided.
5. **Burned-in Chinese subtitle removal**: this MVP detects/blocks it rather than inventing destructive inpainting inside step 09. Supply a safely preprocessed MAIN_SOURCE before production.

These are external content/service dependencies, not silently fabricated capabilities.
