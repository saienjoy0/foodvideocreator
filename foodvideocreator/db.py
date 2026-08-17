from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any

SCHEMA = r"""
PRAGMA foreign_keys = ON;
PRAGMA journal_mode = WAL;

CREATE TABLE IF NOT EXISTS projects (
    project_id TEXT PRIMARY KEY,
    main_source_sha256 TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS workflow_state (
    project_id TEXT PRIMARY KEY REFERENCES projects(project_id) ON DELETE CASCADE,
    workflow_revision INTEGER NOT NULL DEFAULT 0,
    stage TEXT NOT NULL DEFAULT 'READY',
    substate TEXT NOT NULL DEFAULT 'READY',
    open_gate_id TEXT,
    audit_seq INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS assets (
    asset_id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL REFERENCES projects(project_id) ON DELETE CASCADE,
    role TEXT NOT NULL,
    path TEXT NOT NULL,
    sha256 TEXT NOT NULL,
    metadata_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS artifacts (
    artifact_id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL REFERENCES projects(project_id) ON DELETE CASCADE,
    artifact_type TEXT NOT NULL,
    version INTEGER NOT NULL,
    path TEXT NOT NULL,
    sha256 TEXT NOT NULL,
    created_by_run_id TEXT,
    step_fingerprint TEXT,
    metadata_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(project_id, artifact_type, version)
);

CREATE TABLE IF NOT EXISTS artifact_dependencies (
    artifact_id TEXT NOT NULL REFERENCES artifacts(artifact_id) ON DELETE CASCADE,
    depends_on_artifact_id TEXT NOT NULL REFERENCES artifacts(artifact_id) ON DELETE RESTRICT,
    depends_on_sha256 TEXT NOT NULL,
    PRIMARY KEY(artifact_id, depends_on_artifact_id)
);

CREATE TABLE IF NOT EXISTS artifact_slots (
    project_id TEXT NOT NULL REFERENCES projects(project_id) ON DELETE CASCADE,
    slot TEXT NOT NULL,
    current_candidate_id TEXT REFERENCES artifacts(artifact_id),
    current_approved_id TEXT REFERENCES artifacts(artifact_id),
    change_pending INTEGER NOT NULL DEFAULT 0,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY(project_id, slot)
);

CREATE TABLE IF NOT EXISTS checks (
    check_id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id TEXT NOT NULL REFERENCES projects(project_id) ON DELETE CASCADE,
    check_type TEXT NOT NULL,
    artifact_id TEXT REFERENCES artifacts(artifact_id),
    artifact_sha256 TEXT,
    measurement_json TEXT NOT NULL DEFAULT '{}',
    result TEXT NOT NULL,
    blocking INTEGER NOT NULL DEFAULT 1,
    rule_version TEXT NOT NULL DEFAULT 'v1',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS presentations (
    presentation_id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL REFERENCES projects(project_id) ON DELETE CASCADE,
    gate_id TEXT NOT NULL,
    artifact_id TEXT NOT NULL REFERENCES artifacts(artifact_id),
    artifact_sha256 TEXT NOT NULL,
    presented_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS gates (
    gate_id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL REFERENCES projects(project_id) ON DELETE CASCADE,
    stage TEXT NOT NULL,
    artifact_id TEXT NOT NULL REFERENCES artifacts(artifact_id),
    artifact_sha256 TEXT NOT NULL,
    presentation_id TEXT,
    status TEXT NOT NULL DEFAULT 'OPEN',
    opened_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    decided_at TEXT
);

CREATE UNIQUE INDEX IF NOT EXISTS one_open_gate_per_project
ON gates(project_id) WHERE status='OPEN';

CREATE TABLE IF NOT EXISTS directives (
    directive_id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id TEXT NOT NULL REFERENCES projects(project_id) ON DELETE CASCADE,
    directive_type TEXT NOT NULL,
    value_json TEXT NOT NULL,
    active INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE UNIQUE INDEX IF NOT EXISTS one_active_directive_type
ON directives(project_id, directive_type) WHERE active=1;

CREATE TABLE IF NOT EXISTS runs (
    run_id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL REFERENCES projects(project_id) ON DELETE CASCADE,
    activity_type TEXT NOT NULL,
    based_on_workflow_revision INTEGER NOT NULL,
    step_fingerprint TEXT,
    idempotency_key TEXT,
    status TEXT NOT NULL,
    error TEXT,
    started_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    completed_at TEXT
);

CREATE UNIQUE INDEX IF NOT EXISTS successful_idempotency_key
ON runs(project_id, idempotency_key)
WHERE status='COMPLETE' AND idempotency_key IS NOT NULL;

CREATE TABLE IF NOT EXISTS events (
    audit_seq INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id TEXT NOT NULL REFERENCES projects(project_id) ON DELETE CASCADE,
    event_type TEXT NOT NULL,
    payload_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
"""


def init_db(path: str | Path) -> sqlite3.Connection:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(path)
    con.row_factory = sqlite3.Row
    con.executescript(SCHEMA)
    return con


def create_project(con: sqlite3.Connection, project_id: str, main_source_sha256: str | None = None) -> None:
    con.execute("INSERT INTO projects(project_id, main_source_sha256) VALUES(?, ?)", (project_id, main_source_sha256))
    con.execute("INSERT INTO workflow_state(project_id) VALUES(?)", (project_id,))
    emit_event(con, project_id, "PROJECT_CREATED", {"main_source_sha256": main_source_sha256})
    con.commit()


def emit_event(con: sqlite3.Connection, project_id: str, event_type: str, payload: dict[str, Any] | None = None) -> int:
    cur = con.execute(
        "INSERT INTO events(project_id, event_type, payload_json) VALUES(?,?,?)",
        (project_id, event_type, json.dumps(payload or {}, ensure_ascii=False, sort_keys=True)),
    )
    seq = int(cur.lastrowid)
    con.execute("UPDATE workflow_state SET audit_seq=? WHERE project_id=?", (seq, project_id))
    return seq


def get_workflow_revision(con: sqlite3.Connection, project_id: str) -> int:
    row = con.execute("SELECT workflow_revision FROM workflow_state WHERE project_id=?", (project_id,)).fetchone()
    if row is None:
        raise KeyError(project_id)
    return int(row[0])


def bump_workflow_revision(con: sqlite3.Connection, project_id: str, expected: int) -> int:
    cur = con.execute(
        "UPDATE workflow_state SET workflow_revision=workflow_revision+1 WHERE project_id=? AND workflow_revision=?",
        (project_id, expected),
    )
    if cur.rowcount != 1:
        raise RuntimeError("STALE_RUN")
    return expected + 1


def set_state(con: sqlite3.Connection, project_id: str, stage: str, substate: str) -> None:
    con.execute("UPDATE workflow_state SET stage=?, substate=? WHERE project_id=?", (stage, substate, project_id))


def get_state(con: sqlite3.Connection, project_id: str) -> dict[str, Any]:
    row = con.execute("SELECT * FROM workflow_state WHERE project_id=?", (project_id,)).fetchone()
    if row is None:
        raise KeyError(project_id)
    return dict(row)
