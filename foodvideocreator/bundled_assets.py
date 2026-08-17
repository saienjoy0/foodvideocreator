from __future__ import annotations

import hashlib
from pathlib import Path

FIXED_BGM_SHA256 = "0c6625282b69f829b057086e8e37b8baa3f77e7b3b094e372dac89ac78abcdf8"


def verify_fixed_bgm(path: str | Path = "assets/fixed_bgm.MP3") -> Path:
    """Verify the production fixed BGM by its approved SHA-256."""
    p = Path(path)
    if not p.exists() or p.stat().st_size <= 0:
        raise FileNotFoundError("FIXED_BGM_ASSET_REQUIRED")
    sha = hashlib.sha256(p.read_bytes()).hexdigest()
    if sha != FIXED_BGM_SHA256:
        raise RuntimeError(f"FIXED_BGM_SHA256_MISMATCH:{sha}")
    return p


# Backward-compatible name for existing callers.
verify_private_fixed_bgm = verify_fixed_bgm
