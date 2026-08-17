from pathlib import Path
import pytest
from foodvideocreator.db import init_db,create_project
from foodvideocreator.artifacts import write_json_artifact
from foodvideocreator.assets import import_asset
from foodvideocreator.runner import PipelineApp
from foodvideocreator.providers import MockAIProvider,MockVoiceProvider,MockImageProvider


def test_artifact_paths_are_project_namespaced(tmp_path):
    con=init_db(tmp_path/'j.db'); create_project(con,'a'); create_project(con,'b')
    aa=write_json_artifact(con,project_id='a',artifact_type='X',data={'a':1},artifact_root=tmp_path/'art',slot='X')
    bb=write_json_artifact(con,project_id='b',artifact_type='X',data={'b':1},artifact_root=tmp_path/'art',slot='X')
    assert '/a/' in aa['path'].replace('\\','/') and '/b/' in bb['path'].replace('\\','/')
    assert aa['path']!=bb['path']


def test_analysis_rejects_non_main_source(tmp_path):
    main=tmp_path/'main.bin'; other=tmp_path/'other.bin'; main.write_bytes(b'main'); other.write_bytes(b'other')
    con=init_db(tmp_path/'j.db'); create_project(con,'p'); import_asset(con,project_id='p',role='MAIN_SOURCE',path=main)
    app=PipelineApp(con=con,project_id='p',artifact_root=tmp_path/'art',contract_path='workflow/workflow_contract.yaml',ai_provider=MockAIProvider(),voice_provider=MockVoiceProvider(),image_provider=MockImageProvider())
    with pytest.raises(RuntimeError,match='VIDEO_ANALYSIS_MUST_USE_MAIN_SOURCE'):
        app.execute('VIDEO_ANALYSIS',source_path=other)

def test_app_new_main_source_rolls_over_to_new_project(tmp_path):
    a=tmp_path/'a.bin'; b=tmp_path/'b.bin'; a.write_bytes(b'a'); b.write_bytes(b'b')
    con=init_db(tmp_path/'j2.db'); create_project(con,'job')
    app=PipelineApp(con=con,project_id='job',artifact_root=tmp_path/'art2',contract_path='workflow/workflow_contract.yaml',ai_provider=MockAIProvider(),voice_provider=MockVoiceProvider(),image_provider=MockImageProvider())
    first=app.import_user_asset('MAIN_SOURCE',a)
    assert first['new_project'] is False and first['project_id']=='job'
    second=app.import_user_asset('MAIN_SOURCE',b)
    assert second['new_project'] is True
    assert app.project_id==second['project_id'] and app.project_id!='job'
    assert con.execute("SELECT main_source_sha256 FROM projects WHERE project_id=?",(app.project_id,)).fetchone()[0]==second['asset']['sha256']
