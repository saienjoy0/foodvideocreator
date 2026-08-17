import pytest
from foodvideocreator.db import init_db, create_project, get_workflow_revision, bump_workflow_revision
from foodvideocreator.artifacts import register_artifact, get_slot
from foodvideocreator.gates import open_gate, decide_gate, GateError


def setup_project(tmp_path):
    con = init_db(tmp_path / "job.db"); create_project(con, "p1", "source-a")
    register_artifact(con,artifact_id="script_a",project_id="p1",artifact_type="SCRIPT_FINAL",version=1,path="a.json",sha256="sha-a",slot="SCRIPT_FINAL"); return con


def test_only_one_open_gate(tmp_path):
    con = setup_project(tmp_path); open_gate(con, project_id="p1", gate_id="g1", stage="SCRIPT_FINAL", artifact_id="script_a", presentation_id="pres1")
    with pytest.raises(GateError, match="OPEN_GATE_ALREADY_EXISTS"): open_gate(con, project_id="p1", gate_id="g2", stage="SCRIPT_FINAL", artifact_id="script_a", presentation_id="pres2")


def test_candidate_does_not_replace_approved(tmp_path):
    con = setup_project(tmp_path); open_gate(con, project_id="p1", gate_id="g1", stage="SCRIPT_FINAL", artifact_id="script_a", presentation_id="pres1"); decide_gate(con, project_id="p1", gate_id="g1", presentation_id="pres1", artifact_sha256="sha-a", decision="APPROVE")
    register_artifact(con,artifact_id="script_b",project_id="p1",artifact_type="SCRIPT_FINAL",version=2,path="b.json",sha256="sha-b",slot="SCRIPT_FINAL")
    slot = get_slot(con, "p1", "SCRIPT_FINAL"); assert slot["current_candidate_id"] == "script_b"; assert slot["current_approved_id"] == "script_a"; assert slot["change_pending"] == 0


def test_revision_request_marks_pending_without_fake_candidate(tmp_path):
    con = setup_project(tmp_path); open_gate(con, project_id="p1", gate_id="g1", stage="SCRIPT_FINAL", artifact_id="script_a", presentation_id="pres1"); decide_gate(con, project_id="p1", gate_id="g1", presentation_id="pres1", artifact_sha256="sha-a", decision="APPROVE")
    open_gate(con, project_id="p1", gate_id="g2", stage="SCRIPT_FINAL", artifact_id="script_a", presentation_id="pres2"); decide_gate(con, project_id="p1", gate_id="g2", presentation_id="pres2", artifact_sha256="sha-a", decision="REQUEST_REVISION")
    slot = get_slot(con, "p1", "SCRIPT_FINAL"); assert slot["current_candidate_id"] == "script_a"; assert slot["current_approved_id"] == "script_a"; assert slot["change_pending"] == 1


def test_presentation_binding_prevents_wrong_sha(tmp_path):
    con = setup_project(tmp_path); open_gate(con, project_id="p1", gate_id="g1", stage="SCRIPT_FINAL", artifact_id="script_a", presentation_id="pres1")
    with pytest.raises(GateError, match="ARTIFACT_BINDING_MISMATCH"): decide_gate(con, project_id="p1", gate_id="g1", presentation_id="pres1", artifact_sha256="sha-b", decision="APPROVE")


def test_workflow_revision_guard(tmp_path):
    con = setup_project(tmp_path); assert get_workflow_revision(con, "p1") == 0; bump_workflow_revision(con, "p1", 0); assert get_workflow_revision(con, "p1") == 1
    with pytest.raises(RuntimeError, match="STALE_RUN"): bump_workflow_revision(con, "p1", 0)
