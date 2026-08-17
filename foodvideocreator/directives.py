from __future__ import annotations

import json
import sqlite3
from typing import Any

from .db import bump_workflow_revision, emit_event, get_workflow_revision


def set_directive(con: sqlite3.Connection, project_id: str, directive_type: str, value: Any) -> None:
    rev = get_workflow_revision(con, project_id)
    con.execute("UPDATE directives SET active=0 WHERE project_id=? AND directive_type=? AND active=1", (project_id, directive_type))
    con.execute(
        "INSERT INTO directives(project_id, directive_type, value_json) VALUES(?,?,?)",
        (project_id, directive_type, json.dumps(value, ensure_ascii=False, sort_keys=True)),
    )
    bump_workflow_revision(con, project_id, rev)
    emit_event(con, project_id, "DIRECTIVE_CHANGED", {"type": directive_type, "value": value})
    con.commit()


def get_directive(con: sqlite3.Connection, project_id: str, directive_type: str, default: Any = None) -> Any:
    row = con.execute(
        "SELECT value_json FROM directives WHERE project_id=? AND directive_type=? AND active=1 ORDER BY directive_id DESC LIMIT 1",
        (project_id, directive_type),
    ).fetchone()
    return default if row is None else json.loads(row[0])


def get_directives(con: sqlite3.Connection, project_id: str) -> dict[str, Any]:
    rows = con.execute("SELECT directive_type, value_json FROM directives WHERE project_id=? AND active=1", (project_id,)).fetchall()
    return {r[0]: json.loads(r[1]) for r in rows}
