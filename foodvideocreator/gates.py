from __future__ import annotations

import sqlite3

from .artifacts import get_artifact
from .db import bump_workflow_revision, emit_event, get_workflow_revision


class GateError(RuntimeError):
    pass


def open_gate(con: sqlite3.Connection, *, project_id: str, gate_id: str, stage: str, artifact_id: str, presentation_id: str) -> None:
    existing = con.execute("SELECT gate_id FROM gates WHERE project_id=? AND status='OPEN'", (project_id,)).fetchone()
    if existing is not None:
        raise GateError("OPEN_GATE_ALREADY_EXISTS")
    art = get_artifact(con, artifact_id)
    con.execute(
        "INSERT INTO gates(gate_id,project_id,stage,artifact_id,artifact_sha256,presentation_id,status) VALUES(?,?,?,?,?,?,'OPEN')",
        (gate_id, project_id, stage, artifact_id, art["sha256"], presentation_id),
    )
    con.execute(
        "INSERT INTO presentations(presentation_id,project_id,gate_id,artifact_id,artifact_sha256) VALUES(?,?,?,?,?)",
        (presentation_id, project_id, gate_id, artifact_id, art["sha256"]),
    )
    con.execute("UPDATE workflow_state SET open_gate_id=?, substate=? WHERE project_id=?", (gate_id, f"WAITING_{stage}", project_id))
    emit_event(con, project_id, "GATE_OPENED", {"gate_id": gate_id, "artifact_id": artifact_id, "presentation_id": presentation_id})
    con.commit()


def decide_gate(con: sqlite3.Connection, *, project_id: str, gate_id: str, presentation_id: str, artifact_sha256: str, decision: str) -> None:
    if decision not in {"APPROVE", "REQUEST_REVISION"}:
        raise GateError("INVALID_DECISION")
    gate = con.execute("SELECT * FROM gates WHERE gate_id=? AND project_id=? AND status='OPEN'", (gate_id, project_id)).fetchone()
    if gate is None:
        raise GateError("OPEN_GATE_NOT_FOUND")
    presentation = con.execute("SELECT * FROM presentations WHERE presentation_id=? AND gate_id=?", (presentation_id, gate_id)).fetchone()
    if presentation is None:
        raise GateError("PRESENTATION_MISMATCH")
    if gate["presentation_id"] != presentation_id or gate["artifact_sha256"] != artifact_sha256 or presentation["artifact_sha256"] != artifact_sha256:
        raise GateError("ARTIFACT_BINDING_MISMATCH")
    artifact = con.execute("SELECT * FROM artifacts WHERE artifact_id=?", (gate["artifact_id"],)).fetchone()
    if artifact is None or artifact["sha256"] != artifact_sha256:
        raise GateError("ARTIFACT_BINDING_MISMATCH")
    slot = con.execute("SELECT * FROM artifact_slots WHERE project_id=? AND current_candidate_id=?", (project_id, gate["artifact_id"])).fetchone()
    rev = get_workflow_revision(con, project_id)
    if decision == "APPROVE":
        con.execute("UPDATE gates SET status='APPROVED', decided_at=CURRENT_TIMESTAMP WHERE gate_id=?", (gate_id,))
        if slot is not None:
            con.execute("UPDATE artifact_slots SET current_approved_id=?, change_pending=0, updated_at=CURRENT_TIMESTAMP WHERE project_id=? AND slot=?", (gate["artifact_id"], project_id, slot["slot"]))
    else:
        con.execute("UPDATE gates SET status='REVISION_REQUESTED', decided_at=CURRENT_TIMESTAMP WHERE gate_id=?", (gate_id,))
        if slot is not None:
            con.execute("UPDATE artifact_slots SET change_pending=1, updated_at=CURRENT_TIMESTAMP WHERE project_id=? AND slot=?", (project_id, slot["slot"]))
    bump_workflow_revision(con, project_id, rev)
    con.execute("UPDATE workflow_state SET open_gate_id=NULL WHERE project_id=?", (project_id,))
    emit_event(con, project_id, "GATE_DECIDED", {"gate_id": gate_id, "decision": decision, "artifact_id": gate["artifact_id"], "artifact_sha256": artifact_sha256})
    con.commit()
