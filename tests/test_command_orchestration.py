import subprocess
from foodvideocreator.assets import import_asset
from foodvideocreator.db import init_db,create_project
from foodvideocreator.providers import MockAIProvider,MockVoiceProvider,MockImageProvider
from foodvideocreator.runner import PipelineApp


def make_video(p):
    subprocess.run(['ffmpeg','-y','-f','lavfi','-i','testsrc2=size=180x320:rate=30:duration=3','-f','lavfi','-i','sine=frequency=330:duration=3','-c:v','libx264','-pix_fmt','yuv420p','-c:a','aac',str(p)],check=True,capture_output=True)


def test_ok_executes_exactly_one_next_visible_step(tmp_path):
    src=tmp_path/'v.mp4'; make_video(src)
    con=init_db(tmp_path/'j.db'); create_project(con,'p'); import_asset(con,project_id='p',role='MAIN_SOURCE',path=src)
    app=PipelineApp(con=con,project_id='p',artifact_root=tmp_path/'a',contract_path='workflow/workflow_contract.yaml',ai_provider=MockAIProvider(),voice_provider=MockVoiceProvider(),image_provider=MockImageProvider())
    first=app.handle_user_command('お願い',dish_name='テスト料理')
    assert first['next']['step']=='VIDEO_ANALYSIS'
    second=app.handle_user_command('OK')
    assert second['next']['step']=='RESEARCH_RANKING'
    assert second['next']['gate'] is None
    assert app.handle_user_command('お願い')['status']=='WAITING_RANK_SELECTION'


def test_rank_and_route_commands_execute_only_expected_step(tmp_path):
    src=tmp_path/'v.mp4'; make_video(src)
    con=init_db(tmp_path/'j.db'); create_project(con,'p'); import_asset(con,project_id='p',role='MAIN_SOURCE',path=src)
    app=PipelineApp(con=con,project_id='p',artifact_root=tmp_path/'a',contract_path='workflow/workflow_contract.yaml',ai_provider=MockAIProvider(),voice_provider=MockVoiceProvider(),image_provider=MockImageProvider())
    app.handle_user_command('お願い',dish_name='テスト料理'); app.handle_user_command('OK')
    sel=app.handle_user_command('1位'); assert sel['next']['step']=='SELECTION_CONFIRM'
    draft=app.handle_user_command('OK'); assert draft['next']['step']=='SCRIPT_DRAFT'
    tips=app.handle_user_command('OK'); assert tips['next']['step']=='TIPS'
    cta=app.handle_user_command('誘導しなくていい'); assert cta['next']['step']=='CTA'
