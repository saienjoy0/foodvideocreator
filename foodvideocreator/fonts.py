from __future__ import annotations

from pathlib import Path
from fontTools.ttLib import TTCollection, TTFont

TARGET_FULL_NAME = "Noto Sans Mono CJK JP Bold"


def _full_names(font: TTFont) -> set[str]:
    out = set()
    for n in font["name"].names:
        if n.nameID == 4:
            try: out.add(n.toUnicode())
            except Exception: pass
    return out


def find_font_face(paths: list[str | Path] | None = None, target: str = TARGET_FULL_NAME) -> tuple[Path, int | None]:
    candidates = [Path(p) for p in paths] if paths else [
        Path("/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc"),
        Path("/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc"),
    ]
    for path in candidates:
        if not path.exists(): continue
        if path.suffix.lower() in {".ttc", ".otc"}:
            col = TTCollection(str(path))
            found=None
            try:
                for idx, font in enumerate(col.fonts):
                    if target in _full_names(font):
                        found=idx; break
            finally:
                col.close()
            if found is not None:
                return path, found
        else:
            font = TTFont(str(path))
            try:
                matched=target in _full_names(font)
            finally:
                font.close()
            if matched:
                return path, None
    raise RuntimeError(f"FONT_FULL_NAME_NOT_FOUND:{target}")
