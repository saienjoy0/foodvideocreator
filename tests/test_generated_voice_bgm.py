import subprocess
from pathlib import Path

from foodvideocreator.assets import import_asset
from foodvideocreator.db import init_db, create_project
from foodvideocreator.directives import set_directive
from foodvideocreator.providers import MockAIProvider, MockImageProvider, MockVoiceProvider
from foodvideocreator.runner import PipelineApp

class CountingVoice(MockVoiceProvider):
    def __init__(self): self.calls=0
    def synthesize(self,*a,**k): self.calls+=1; return super().synthesize(*a,**k)

def make_video(path,duration=6):
    subprocess.run(['ffmpeg','-y','-f','lavfi','-i',f'testsrc2=size=240x426:rate=30:duration={duration}','-f','lavfi','-i',f'sine=frequency=330:duration={duration}','-c:v','libx264','-pix_fmt','yuv420p','-c:a','aac',str(path)],check=True,capture_output=True)

def make_test_bgm(path,duration=6):
    subprocess.run(['ffmpeg','-y','-f','lavfi','-i',f'sine=frequency=220:duration={duration}','-c:a','libmp3lame','-b:a','64k',str(path)],check=True,capture_output=True)

def approve(app,out):
    assert out['gate'] and not out['gate'].get('blocked_checks'); app.approve_open_gate()

def prepare_to_final(app,con,source):
    approve(app,app.execute('VIDEO_ANALYSIS',source_path=source,dish_name='音声料理'))
    app.execute('RESEARCH_RANKING'); approve(app,app.execute('SELECTION_CONFIRM',ranks=[1])); approve(app,app.execute('SCRIPT_DRAFT'))
    app.execute('TIPS'); app.execute('ROUTE_SELECTION',route='A'); approve(app,app.execute('CTA',cta_none=True))

def test_generated_voice_and_fixed_bgm(tmp_path):
    source=tmp_path/'source.mp4'; bgm=tmp_path/'fixed_bgm.MP3'; make_video(source); make_test_bgm(bgm)
    con=init_db(tmp_path/'job.db'); create_project(con,'p')
    import_asset(con,project_id='p',role='MAIN_SOURCE',path=source); import_asset(con,project_id='p',role='BGM_ASSET',path=bgm,metadata={'kind':'FIXED'})
    voice=CountingVoice(); app=PipelineApp(con=con,project_id='p',artifact_root=tmp_path/'artifacts',contract_path='workflow/workflow_contract.yaml',ai_provider=MockAIProvider(),voice_provider=voice,image_provider=MockImageProvider())
    prepare_to_final(app,con,source); set_directive(con,'p','AUDIO_POLICY','REPLACE_SPEECH'); set_directive(con,'p','BGM_POLICY','FIXED')
    out=app.execute('SCRIPT_FINAL'); assert out['result']['voice_preflight']['result']=='PASS'; approve(app,out)
    prod=app.execute('PRODUCTION'); assert prod['result']['machine_qa']=='PASS'; assert voice.calls==1
    app.approve_open_gate(decision='REQUEST_REVISION'); prod2=app.execute('PRODUCTION'); assert prod2['result']['machine_qa']=='PASS'; assert voice.calls==1
