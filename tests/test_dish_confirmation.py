import subprocess
from foodvideocreator.db import init_db, create_project
from foodvideocreator.assets import import_asset
from foodvideocreator.runner import PipelineApp
from foodvideocreator.providers import MockVoiceProvider, MockImageProvider, MockAIProvider

class LowConfidenceAI(MockAIProvider):
    def video_semantic_analysis(self,payload):
        d=super().video_semantic_analysis(payload); d["dish_identity_confidence"]=.55; return d


def test_low_identity_waits_for_user_then_can_be_confirmed(tmp_path):
    v=tmp_path/"v.mp4"
    subprocess.run(["ffmpeg","-y","-f","lavfi","-i","testsrc2=size=180x320:rate=15:duration=1","-c:v","libx264","-pix_fmt","yuv420p",str(v)],check=True,capture_output=True)
    con=init_db(tmp_path/"job.db"); create_project(con,"p",None); import_asset(con,project_id="p",role="MAIN_SOURCE",path=v)
    app=PipelineApp(con=con,project_id="p",artifact_root=tmp_path/"a",contract_path="workflow/workflow_contract.yaml",ai_provider=LowConfidenceAI(),voice_provider=MockVoiceProvider(),image_provider=MockImageProvider())
    out=app.execute("VIDEO_ANALYSIS",source_path=v)
    assert out["gate"]["blocked_checks"]==["CHECK_DISH_IDENTITY"]
    fixed=app.confirm_dish_identity("確認済み料理")
    assert fixed["gate"]["gate_id"]
