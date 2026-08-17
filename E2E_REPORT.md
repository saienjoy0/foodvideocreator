# E2E Verification Report

Design target: v1.6.2 Final MVP Contract

## Verified scenarios

| Scenario | Result |
|---|---|
| Contract validation — 17 formal steps | PASS |
| Current v4 rules — 19 files | PASS |
| One Open Gate only | PASS |
| Presentation/SHA approval binding | PASS |
| Candidate does not replace approved artifact | PASS |
| Revision request sets change_pending | PASS |
| Dish Identity <0.80 blocks Research | PASS |
| User Dish confirmation creates new Analysis version | PASS |
| Claim Evidence invalid → Research blocked | PASS |
| Script Lab structure gate | PASS |
| Draft/Tips/Final density gates | PASS |
| A/CTA-none command orchestration | PASS |
| Display/spoken pronunciation separation | PASS |
| Generated Voice actual-duration path | PASS |
| Voice fingerprint reuse | PASS |
| fixed BGM global asset | PASS |
| ASMR missing asset → block | PASS |
| Subtitle low-resolution proportional layout | PASS |
| Route A full E2E → Final | PASS |
| Route B → BASE → 13A → 13B → Final | PASS |
| EXTERNAL_RENDER → Video Gate | PASS |
| New MAIN_SOURCE → new project rollover | PASS |
| Project artifact physical isolation | PASS |
| Exact 13B font Full Name | PASS |
| 13B bbox + 270×480 preview | PASS |
| Final normal tail | PASS |
| Final complete-black-tail replacement | PASS |
| Final decoded audio content unchanged | PASS |
| Final representative video body unchanged | PASS |
| External command AI adapter | PASS |
| External command Voice adapter | PASS |
| External command Image adapter | PASS |

## Full test suite

Latest complete monitored run:

```text
53 passed in 32.96s
```

## Environment observations

```text
ffmpeg: /usr/bin/ffmpeg
ffprobe: /usr/bin/ffprobe
Noto Sans Mono CJK JP Bold: found
TTC index in this environment: 5
fixed_bgm.MP3 duration: 39.288125 seconds
```

TTC index is **not hard-coded**; it is enumerated from the font collection each run.

## External-service boundary

The E2E suite uses deterministic Mock Providers and separately verifies the subprocess Command Provider protocol. It does not claim that a third-party production AI/TTS/image provider is configured. A production provider must implement `docs/PROVIDER_PROTOCOL.md`.
