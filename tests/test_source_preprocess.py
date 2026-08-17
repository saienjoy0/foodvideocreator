import pytest
from foodvideocreator.db import init_db, create_project
from foodvideocreator.artifacts import write_json_artifact
from foodvideocreator.activities.production import run_production
from foodvideocreator.providers.mock import MockAIProvider, MockVoiceProvider


def _approved_analysis(con, root, project, preprocess, audio_present=True):
    art=write_json_artifact(con,project_id=project,artifact_type='ANALYSIS',slot='ANALYSIS',artifact_root=root,filename='analysis.json',data={'video': {'duration': 6.0, 'audio_present': audio_present},'source_preprocess': preprocess})
    con.execute("UPDATE artifact_slots SET current_approved_id=? WHERE project_id=? AND slot='ANALYSIS'",(art['artifact_id'],project));con.commit(); return art


def _call_until_preprocess(con, root, project):
    with pytest.raises(RuntimeError) as exc: run_production(con,project_id=project,artifact_root=root,provider=MockAIProvider(),voice_provider=MockVoiceProvider())
    return str(exc.value)


def test_preprocess_missing_fields_blocks(tmp_path):
    con=init_db(tmp_path/'j.db');create_project(con,'p',None); art=_approved_analysis(con,tmp_path/'a','p',{'burned_in_subtitle':False})
    assert _call_until_preprocess(con,tmp_path/'a','p')=='SOURCE_PREPROCESS_ANALYSIS_INCOMPLETE'
    row=con.execute("SELECT result FROM checks WHERE project_id=? AND check_type='CHECK_SOURCE_PREPROCESS' AND artifact_id=? ORDER BY check_id DESC LIMIT 1",('p',art['artifact_id'])).fetchone(); assert row['result']=='BLOCKED'


def test_burned_in_subtitle_requires_preprocess(tmp_path):
    con=init_db(tmp_path/'j.db');create_project(con,'p',None); art=_approved_analysis(con,tmp_path/'a','p',{'burned_in_subtitle':True,'logo':False,'ui':False,'black_frame':False,'video_corruption':False,'subtitle_removal_risk':'PREPROCESS'})
    assert _call_until_preprocess(con,tmp_path/'a','p')=='SOURCE_PREPROCESS_REQUIRED'
    row=con.execute("SELECT result FROM checks WHERE project_id=? AND check_type='CHECK_SOURCE_PREPROCESS' AND artifact_id=? ORDER BY check_id DESC LIMIT 1",('p',art['artifact_id'])).fetchone(); assert row['result']=='BLOCKED'


def test_user_decision_preprocess_blocks(tmp_path):
    con=init_db(tmp_path/'j.db');create_project(con,'p',None); _approved_analysis(con,tmp_path/'a','p',{'burned_in_subtitle':True,'logo':False,'ui':False,'black_frame':False,'video_corruption':False,'subtitle_removal_risk':'USER_DECISION_REQUIRED'})
    assert _call_until_preprocess(con,tmp_path/'a','p')=='SOURCE_PREPROCESS_USER_DECISION_REQUIRED'
