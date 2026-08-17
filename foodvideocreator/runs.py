from __future__ import annotations

import hashlib
import json
import sqlite3
import uuid
from typing import Any

from .db import emit_event, get_workflow_revision

def fingerprint(parts: dict[str, Any]) -> str:
    return hashlib.sha256(json.dumps(parts,ensure_ascii=False,sort_keys=True,separators=(",",":")).encode()).hexdigest()

def begin_run(con: sqlite3.Connection, project_id: str, activity_type: str, step_fingerprint: str | None) -> dict[str, Any]:
    revision=get_workflow_revision(con,project_id)
    key=f"{project_id}:{activity_type}:{step_fingerprint}" if step_fingerprint else None
    if key:
        row=con.execute("SELECT * FROM runs WHERE project_id=? AND idempotency_key=? AND status='COMPLETE'",(project_id,key)).fetchone()
        if row:return {**dict(row),"reused":True}
    rid=f"run_{uuid.uuid4().hex[:12]}"
    con.execute("INSERT INTO runs(run_id,project_id,activity_type,based_on_workflow_revision,step_fingerprint,idempotency_key,status) VALUES(?,?,?,?,?,?,'RUNNING')",(rid,project_id,activity_type,revision,step_fingerprint,key))
    emit_event(con,project_id,"RUN_STARTED",{"run_id":rid,"activity_type":activity_type,"workflow_revision":revision})
    con.commit()
    return {"run_id":rid,"based_on_workflow_revision":revision,"idempotency_key":key,"reused":False}

def complete_run(con: sqlite3.Connection, project_id: str, run_id: str) -> None:
    row=con.execute("SELECT based_on_workflow_revision FROM runs WHERE run_id=?",(run_id,)).fetchone()
    if row is None: raise KeyError(run_id)
    if get_workflow_revision(con,project_id)!=int(row[0]):
        con.execute("UPDATE runs SET status='STALE_RUN',completed_at=CURRENT_TIMESTAMP,error='workflow_revision_changed' WHERE run_id=?",(run_id,))
        emit_event(con,project_id,"RUN_STALE",{"run_id":run_id}); con.commit(); raise RuntimeError("STALE_RUN")
    con.execute("UPDATE runs SET status='COMPLETE',completed_at=CURRENT_TIMESTAMP WHERE run_id=?",(run_id,))
    emit_event(con,project_id,"RUN_COMPLETED",{"run_id":run_id}); con.commit()

def fail_run(con: sqlite3.Connection, project_id: str, run_id: str, error: str, retryable: bool=False) -> None:
    status="FAILED_RETRYABLE" if retryable else "FAILED_BLOCKED"
    con.execute("UPDATE runs SET status=?,completed_at=CURRENT_TIMESTAMP,error=? WHERE run_id=?",(status,error,run_id))
    emit_event(con,project_id,"RUN_FAILED",{"run_id":run_id,"status":status,"error":error}); con.commit()
