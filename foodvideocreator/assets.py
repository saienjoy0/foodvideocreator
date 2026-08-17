from __future__ import annotations

import json
import sqlite3
import uuid
from pathlib import Path
from typing import Any

from .artifacts import sha256_file
from .db import bump_workflow_revision, emit_event, get_workflow_revision


def import_asset(con: sqlite3.Connection, *, project_id: str, role: str, path: str | Path, metadata: dict[str, Any] | None = None) -> dict[str, Any]:
    p=Path(path)
    if not p.exists() or p.stat().st_size<=0: raise ValueError("ASSET_INVALID")
    sha=sha256_file(p); aid=f"asset_{uuid.uuid4().hex[:12]}"
    old=None
    if role=="MAIN_SOURCE":
        row=con.execute("SELECT main_source_sha256 FROM projects WHERE project_id=?",(project_id,)).fetchone()
        old=row[0] if row else None
        # Reject before inserting anything. A different MAIN_SOURCE is a new job,
        # not an asset mutation inside the current job.
        if old and old!=sha:
            raise RuntimeError("NEW_PROJECT_REQUIRED")
    con.execute("INSERT INTO assets(asset_id,project_id,role,path,sha256,metadata_json) VALUES(?,?,?,?,?,?)", (aid,project_id,role,str(p),sha,json.dumps(metadata or {},ensure_ascii=False,sort_keys=True)))
    if role=="MAIN_SOURCE" and old != sha:
        rev=get_workflow_revision(con,project_id)
        con.execute("UPDATE projects SET main_source_sha256=? WHERE project_id=?",(sha,project_id))
        bump_workflow_revision(con,project_id,rev)
    emit_event(con,project_id,"ASSET_IMPORTED",{"asset_id":aid,"role":role,"sha256":sha})
    con.commit()
    return {"asset_id":aid,"role":role,"path":str(p),"sha256":sha,"metadata":metadata or {}}


def latest_asset(con: sqlite3.Connection, project_id: str, role: str) -> dict[str, Any] | None:
    row=con.execute("SELECT * FROM assets WHERE project_id=? AND role=? ORDER BY created_at DESC,rowid DESC LIMIT 1",(project_id,role)).fetchone()
    if row is None:return None
    d=dict(row); d["metadata"]=json.loads(d.pop("metadata_json")); return d
