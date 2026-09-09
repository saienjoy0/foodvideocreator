#!/usr/bin/env python3
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

MODEL = os.environ.get("GEMINI_RESEARCH_MODEL", "gemini-2.5-flash")
API_KEY = os.environ.get("GEMINI_API_KEY", "").strip()
API_URL = f"https://generativelanguage.googleapis.com/v1beta/models/{MODEL}:generateContent"

BASE_PROMPT = r'''あなたはAmazon Area Managerのキャリア調査を行うリサーチャーです。
与えられた公開YouTube動画を実際に解析し、動画内で本人が話した内容だけを根拠に、日本語で詳細に整理してください。

絶対条件:
- 動画説明欄や一般知識だけで埋めず、動画内容を優先する。
- 本人が言っていないことを推測で補わない。
- 推測・解釈をする場合は「解釈」と明示し、本人発言と分離する。
- 数字（勤務時間、給与、人数、昇進期間、KPI、日数、%など）は可能な限り正確に拾う。
- 重要箇所にはタイムスタンプを付ける。
- 長い逐語転載ではなく、発言内容を忠実に日本語化・要約する。短い重要フレーズのみ引用可。
- 不明な項目は「動画内では言及なし」と書く。

以下を必ず抽出する:
1. 投稿者の立場・拠点種別（FC/DS/SC等）・在籍期間
2. Area Managerとして実際に何をしていたか
3. 1日の流れ、勤務時間、残業、日勤/夜勤、週何日勤務か
4. 管理人数・PA/AA/OM等との役割分担
5. KPI、Rates、安全、品質、勤怠、People Managementの実態
6. 最も大変だったこと・嫌だったこと
7. 良かったこと・成長した能力
8. Work-Life Balance
9. 給与・RSU/株式・昇給について本人が話した内容
10. L4→L5→L6の昇進速度・条件・評価・スポンサーについて
11. Project Management/改善プロジェクトの自由度
12. Internal Transfer、Corporate、Program Manager、Central Ops等への異動について
13. 退職した場合の理由と次のキャリア
14. 本人がAMを勧めるか、どんな人に向く/向かないと言っているか
15. 日本の新卒Amazon Area Manager候補者が進路判断する際に重要な「事実」

出力形式:
# 動画情報
- タイトル:
- 投稿者:
- 動画URL:
- 動画内で確認できる本人属性:

# 時系列詳細
## [00:00-xx:xx]
- 本人が話している内容:
- 重要な事実・数字:
- 短い重要発言（必要な場合のみ）:

（動画全体を最後まで続ける）

# テーマ別抽出
上記1〜15をそれぞれ詳しく。

# 進路判断用サマリー
- 強いメリット
- 強いデメリット
- 想像と違いそうな点
- 1〜2年働く価値
- 3〜5年働く価値
- AM→L5/L6の現実性
- AM→Corporate/Program Managerの証拠
- この動画単体からは判断できないこと

最後に「本人発言として確実」「本人の一例にすぎない」「動画内では不明」の3区分で箇条書き整理してください。
'''


def slugify(value: str) -> str:
    value = re.sub(r"[^A-Za-z0-9_-]+", "_", value.strip())
    return value.strip("_") or "video"


def gemini(video_url: str, prompt: str, max_output_tokens: int = 8192) -> str:
    if not API_KEY:
        raise RuntimeError("GEMINI_API_KEY is missing")
    payload = {
        "contents": [{
            "parts": [
                {"text": prompt},
                {"file_data": {"file_uri": video_url}}
            ]
        }],
        "generationConfig": {
            "temperature": 0.15,
            "maxOutputTokens": max_output_tokens
        }
    }
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(
        API_URL,
        data=data,
        method="POST",
        headers={
            "Content-Type": "application/json",
            "x-goog-api-key": API_KEY,
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=900) as resp:
            obj = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"Gemini HTTP {e.code}: {body[:4000]}") from e

    texts = []
    for cand in obj.get("candidates", []):
        for part in cand.get("content", {}).get("parts", []):
            if isinstance(part, dict) and part.get("text"):
                texts.append(part["text"])
    if not texts:
        raise RuntimeError("Gemini returned no text: " + json.dumps(obj, ensure_ascii=False)[:4000])
    return "\n".join(texts).strip()


def gemini_text(prompt: str, max_output_tokens: int = 8192) -> str:
    if not API_KEY:
        raise RuntimeError("GEMINI_API_KEY is missing")
    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {"temperature": 0.15, "maxOutputTokens": max_output_tokens},
    }
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(
        API_URL, data=data, method="POST",
        headers={"Content-Type": "application/json", "x-goog-api-key": API_KEY},
    )
    try:
        with urllib.request.urlopen(req, timeout=900) as resp:
            obj = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"Gemini HTTP {e.code}: {body[:4000]}") from e
    texts = []
    for cand in obj.get("candidates", []):
        for part in cand.get("content", {}).get("parts", []):
            if isinstance(part, dict) and part.get("text"):
                texts.append(part["text"])
    if not texts:
        raise RuntimeError("Gemini returned no text")
    return "\n".join(texts).strip()


def main() -> int:
    if len(sys.argv) != 2:
        print("usage: run_youtube_research.py request.json", file=sys.stderr)
        return 2
    request_path = Path(sys.argv[1])
    req = json.loads(request_path.read_text(encoding="utf-8"))
    videos = req.get("videos", [])
    if not videos:
        raise RuntimeError("No videos in request")

    stem = slugify(request_path.stem)
    outdir = Path("research_results") / stem
    outdir.mkdir(parents=True, exist_ok=True)
    manifest = {
        "request": str(request_path),
        "model": MODEL,
        "videos": [],
    }
    analyses = []

    for idx, video in enumerate(videos, start=1):
        title = video["title"]
        url = video["url"]
        vid = slugify(video.get("id", f"video_{idx:02d}"))
        focus = video.get("focus", "")
        prompt = BASE_PROMPT + "\n\n今回特に重点的に確認する論点:\n" + focus + f"\n\n対象動画タイトル: {title}\n対象URL: {url}\n"
        print(f"[{idx}/{len(videos)}] analyzing {title}", flush=True)
        try:
            text = gemini(url, prompt)
            status = "completed"
        except Exception as exc:
            text = f"# ERROR\n\n{type(exc).__name__}: {exc}\n"
            status = "failed"
        path = outdir / f"{idx:02d}_{vid}.md"
        path.write_text(f"# {title}\n\nURL: {url}\n\n{text}\n", encoding="utf-8")
        manifest["videos"].append({"title": title, "url": url, "file": str(path), "status": status})
        if status == "completed":
            analyses.append(f"\n\n===== VIDEO {idx}: {title} =====\n{text}")
        time.sleep(2)

    if analyses:
        combined_input = "".join(analyses)
        # Keep synthesis input bounded while preserving all completed analyses as much as possible.
        if len(combined_input) > 180000:
            combined_input = combined_input[:180000]
        synthesis_prompt = r'''以下は複数のAmazon Area Manager本人動画をGeminiで個別解析した結果です。
これらを横断比較し、日本の新卒候補者がAmazon Area Managerを進路として判断するための統合レポートを日本語で作ってください。

重要:
- 各動画の本人発言と、横断的な推論を分ける。
- 1人だけが言っていることをAmazon全体の制度として一般化しない。
- 複数人で一致した内容は「複数事例で一致」とする。
- 米国固有の可能性がある制度は明示する。
- 数字は誰の事例か分かるように書く。
- 特に L4→L5→L6、勤務時間、夜勤、People Management、Project、退職理由、Corporate/Program Managerへの出口を厚くする。

必須構成:
# 結論
# 動画別プロフィール比較表
# 仕事内容の共通項
# 勤務時間・夜勤・WLB比較
# People Managementの実態
# KPI・数字・現場作業
# Project Management経験
# L4→L5→L6 昇進の実例
# 退職・辞退理由
# AM経験で得られるスキル
# Corporate / Program Managerへの出口について得られた証拠
# 日本Amazon内定者イベントで追加確認すべき質問
# 確度評価（複数動画一致 / 単一事例 / 不明）
# 進路判断への示唆
'''
        print("creating cross-video synthesis", flush=True)
        try:
            synthesis = gemini_text(synthesis_prompt + "\n\n" + combined_input, max_output_tokens=12288)
        except Exception as exc:
            synthesis = f"# ERROR\n\n{type(exc).__name__}: {exc}\n"
        (outdir / "00_cross_video_synthesis.md").write_text(synthesis + "\n", encoding="utf-8")

    (outdir / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"results: {outdir}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
