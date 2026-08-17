from __future__ import annotations

import re
from typing import Any

APPROVE_WORDS={"ok","オッケー","次へ","それでいい","採用"}
EDITORIAL_OVERRIDE_WORDS={"それでも進めて","企画続行","この企画で続行","弱くても進めて"}


def parse_command(text:str)->dict[str,Any]:
    t=text.strip()
    if t.lower()=="ok" or t in APPROVE_WORDS: return {"intent":"APPROVE"}
    if t in EDITORIAL_OVERRIDE_WORDS: return {"intent":"EDITORIAL_OVERRIDE"}
    if t in {"お願い","開始"}: return {"intent":"START_OR_NEXT"}
    if t=="A": return {"intent":"ROUTE","route":"A"}
    if t=="B": return {"intent":"ROUTE","route":"B"}
    if t=="誘導しなくていい": return {"intent":"ROUTE","route":"A","cta_none":True}
    if t=="BGMなし": return {"intent":"BGM","value":"NONE"}
    if t in {"BGMあり","fixed_bgm"}: return {"intent":"BGM","value":"FIXED"}
    if t=="ASMR": return {"intent":"BGM","value":"ASMR"}
    if t=="字幕": return {"intent":"SUBTITLE_HELPER"}
    if t=="概要": return {"intent":"PUBLISHING"}
    if t=="BASE": return {"intent":"BASE_COPY"}
    if t=="画像": return {"intent":"BASE_IMAGES"}
    if t in {"サムネ"}: return {"intent":"THUMBNAIL_NEXT"}
    if t in {"背景","文字なし","まず文字なし"}: return {"intent":"THUMBNAIL_BG"}
    if t=="文字入れて": return {"intent":"THUMBNAIL_TEXT"}
    if t in {"終了サムネ","最後に入れて"}: return {"intent":"FINAL"}
    if t=="最初から": return {"intent":"RESET"}
    nums=[int(x) for x in re.findall(r"(\d+)\s*位?",t)]
    if nums and all(1<=n<=20 for n in nums): return {"intent":"RANK_SELECTION","ranks":nums}
    return {"intent":"TEXT","text":t}
