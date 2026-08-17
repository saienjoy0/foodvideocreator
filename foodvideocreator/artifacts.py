from __future__ import annotations

import hashlib
import json
import os
import shutil
import sqlite3
import uuid
from pathlib import Path
from typing import Any, Iterable

from .db import emit_event


def sha256_file(path: str | Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()




def project_artifact_root(artifact_root: str | Path, project_id: str) -> Path:
    return Path(artifact_root) / project_id


def next_artifact_version(con: sqlite3.Connection, project_id: str, artifact_type: str) -> int:
    row = con.execute("SELECT COALESCE(MAX(version),0)+1 FROM artifacts WHERE project_id=? AND artifact_type=?", (project_id, artifact_type)).fetchone()
    return int(row[0])


def register_artifact(
    con: sqlite3.Connection,
    *,
    artifact_id: str,
    project_id: str,
    artifact_type: str,
    version: int,
    path: str,
    sha256: str,
    slot: str | None = None,
    created_by_run_id: str | None = None,
    step_fingerprint: str | None = None,
    metadata: dict[str, Any] | None = None,
    dependencies: Iterable[tuple[str, str]] = (),
) -> None:
    con.execute(
        """INSERT INTO artifacts(artifact_id,project_id,artifact_type,version,path,sha256,created_by_run_id,step_fingerprint,metadata_json)
           VALUES(?,?,?,?,?,?,?,?,?)""",
        (artifact_id, project_id, artifact_type, version, path, sha256, created_by_run_id, step_fingerprint, json.dumps(metadata or {}, ensure_ascii=False, sort_keys=True)),
    )
    for dep_id, dep_sha in dependencies:
        con.execute("INSERT INTO artifact_dependencies(artifact_id,depends_on_artifact_id,depends_on_sha256) VALUES(?,?,?)", (artifact_id, dep_id, dep_sha))
    if slot:
        con.execute(
            """INSERT INTO artifact_slots(project_id,slot,current_candidate_id,change_pending)
               VALUES(?,?,?,0)
               ON CONFLICT(project_id,slot) DO UPDATE SET current_candidate_id=excluded.current_candidate_id, updated_at=CURRENT_TIMESTAMP""",
            (project_id, slot, artifact_id),
        )
    emit_event(con, project_id, "ARTIFACT_CREATED", {"artifact_id": artifact_id, "artifact_type": artifact_type, "sha256": sha256, "slot": slot})
    con.commit()


def commit_file_artifact(
    con: sqlite3.Connection,
    *,
    project_id: str,
    artifact_type: str,
    source_path: str | Path,
    artifact_root: str | Path,
    slot: str | None = None,
    created_by_run_id: str | None = None,
    step_fingerprint: str | None = None,
    metadata: dict[str, Any] | None = None,
    dependencies: Iterable[tuple[str, str]] = (),
) -> dict[str, Any]:
    source_path = Path(source_path)
    if not source_path.exists() or source_path.stat().st_size <= 0:
        raise ValueError("ARTIFACT_FILE_INVALID")
    version = next_artifact_version(con, project_id, artifact_type)
    dest_dir = project_artifact_root(artifact_root, project_id) / artifact_type.lower() / f"v{version:03d}"
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / source_path.name
    if source_path.resolve() != dest.resolve():
        tmp = dest.with_suffix(dest.suffix + ".tmp")
        shutil.copy2(source_path, tmp)
        os.replace(tmp, dest)
    sha = sha256_file(dest)
    artifact_id = f"{artifact_type.lower()}_{version:03d}_{uuid.uuid4().hex[:8]}"
    register_artifact(
        con,
        artifact_id=artifact_id,
        project_id=project_id,
        artifact_type=artifact_type,
        version=version,
        path=str(dest),
        sha256=sha,
        slot=slot,
        created_by_run_id=created_by_run_id,
        step_fingerprint=step_fingerprint,
        metadata=metadata,
        dependencies=dependencies,
    )
    return get_artifact(con, artifact_id)


def write_json_artifact(
    con: sqlite3.Connection,
    *,
    project_id: str,
    artifact_type: str,
    data: Any,
    artifact_root: str | Path,
    slot: str | None = None,
    filename: str = "artifact.json",
    **kwargs: Any,
) -> dict[str, Any]:
    staging = project_artifact_root(artifact_root, project_id) / ".staging"
    staging.mkdir(parents=True, exist_ok=True)
    tmp = staging / f"{uuid.uuid4().hex}_{filename}"
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
    try:
        return commit_file_artifact(con, project_id=project_id, artifact_type=artifact_type, source_path=tmp, artifact_root=artifact_root, slot=slot, **kwargs)
    finally:
        tmp.unlink(missing_ok=True)


def get_artifact(con: sqlite3.Connection, artifact_id: str) -> dict[str, Any]:
    row = con.execute("SELECT * FROM artifacts WHERE artifact_id=?", (artifact_id,)).fetchone()
    if row is None:
        raise KeyError(artifact_id)
    d = dict(row)
    d["metadata"] = json.loads(d.pop("metadata_json"))
    return d


def get_slot(con: sqlite3.Connection, project_id: str, slot: str) -> dict[str, Any] | None:
    row = con.execute("SELECT * FROM artifact_slots WHERE project_id=? AND slot=?", (project_id, slot)).fetchone()
    return None if row is None else dict(row)


def get_candidate(con: sqlite3.Connection, project_id: str, slot: str) -> dict[str, Any] | None:
    s = get_slot(con, project_id, slot)
    return None if not s or not s["current_candidate_id"] else get_artifact(con, s["current_candidate_id"])


def get_approved(con: sqlite3.Connection, project_id: str, slot: str, *, allow_pending: bool = False) -> dict[str, Any] | None:
    s = get_slot(con, project_id, slot)
    if not s or not s["current_approved_id"] or (s["change_pending"] and not allow_pending):
        return None
    return get_artifact(con, s["current_approved_id"])


def artifact_is_fresh(con: sqlite3.Connection, artifact_id: str) -> bool:
    rows = con.execute("SELECT depends_on_artifact_id, depends_on_sha256 FROM artifact_dependencies WHERE artifact_id=?", (artifact_id,)).fetchall()
    for dep in rows:
        row = con.execute("SELECT sha256 FROM artifacts WHERE artifact_id=?", (dep[0],)).fetchone()
        if row is None or row[0] != dep[1]:
            return False
    art = get_artifact(con, artifact_id)
    p = Path(art["path"])
    return p.exists() and p.stat().st_size > 0 and sha256_file(p) == art["sha256"]


def find_fresh_by_fingerprint(con: sqlite3.Connection, project_id: str, artifact_type: str, step_fingerprint: str) -> dict[str, Any] | None:
    row=con.execute(
        "SELECT artifact_id FROM artifacts WHERE project_id=? AND artifact_type=? AND step_fingerprint=? ORDER BY version DESC LIMIT 1",
        (project_id,artifact_type,step_fingerprint),
    ).fetchone()
    if not row: return None
    art=get_artifact(con,row[0])
    return art if artifact_is_fresh(con,art["artifact_id"]) else None


def set_candidate(con: sqlite3.Connection, project_id: str, slot: str, artifact_id: str) -> None:
    con.execute(
        """INSERT INTO artifact_slots(project_id,slot,current_candidate_id,change_pending)
           VALUES(?,?,?,0)
           ON CONFLICT(project_id,slot) DO UPDATE SET current_candidate_id=excluded.current_candidate_id,updated_at=CURRENT_TIMESTAMP""",
        (project_id,slot,artifact_id),
    )
    con.commit()
