import json
from pathlib import Path

from foodvideocreator.db import init_db, create_project
from foodvideocreator.runner import PipelineApp
from foodvideocreator.providers.mock import MockAIProvider, MockVoiceProvider, MockImageProvider
from foodvideocreator.assets import import_asset
from foodvideocreator.artifacts import write_json_artifact
from foodvideocreator.checks import record_check

ROOT=Path(__file__).resolve().parents[1]

class BadEvidence(MockAIProvider):
    def research_and_rank(self,payload):
        return {"claims":[{"claim_id":"bad","claim_type":"STORY","claim":"根拠なし","classification":"history","evidence_strength":"high","sources":[]}],"ranking":[{"rank":1,"claim_id":"bad"}]}


def _app(tmp_path, provider=None):
    con=init_db(tmp_path/'job.db');create_project(con,'p',None)
    return con,PipelineApp(con=con,project_id='p',artifact_root=tmp_path/'art',contract_path=ROOT/'workflow/workflow_contract.yaml',ai_provider=provider or MockAIProvider(),voice_provider=MockVoiceProvider(),image_provider=MockImageProvider(),rules_dir=ROOT/'rules/v4')


def test_research_claim_evidence_fail_blocks_step(tmp_path):
    con,app=_app(tmp_path,BadEvidence())
    art=write_json_artifact(con,project_id='p',artifact_type='ANALYSIS',slot='ANALYSIS',artifact_root=tmp_path/'art',filename='analysis.json',data={'dish_identity':'料理','dish_identity_confidence':1.0,'identity_conflict':False})
    con.execute("UPDATE artifact_slots SET current_approved_id=? WHERE project_id='p' AND slot='ANALYSIS'",(art['artifact_id'],));con.commit()
    record_check(con,'p','CHECK_DISH_IDENTITY',artifact_id=art['artifact_id'],artifact_sha256=art['sha256'],measurement={},result='PASS')
    out=app.execute('RESEARCH_RANKING')
    assert out['blocked_checks']==['CHECK_CLAIM_EVIDENCE']
    assert out['next_step'] is None


def test_no_gate_tips_check_failure_is_visible_to_engine(tmp_path):
    con,app=_app(tmp_path)
    art=write_json_artifact(con,project_id='p',artifact_type='TIPS_SCRIPT',slot='TIPS_SCRIPT',artifact_root=tmp_path/'art',filename='tips.json',data={'text':'x'})
    record_check(con,'p','CHECK_SCRIPT_DENSITY_TIPS',artifact_id=art['artifact_id'],artifact_sha256=art['sha256'],measurement={},result='FAIL')
    record_check(con,'p','CHECK_FACT_INTEGRITY',artifact_id=art['artifact_id'],artifact_sha256=art['sha256'],measurement={},result='PASS')
    assert app._blocking_check_failures('TIPS')==['CHECK_SCRIPT_DENSITY_TIPS']
