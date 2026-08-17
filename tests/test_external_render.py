import subprocess
from foodvideocreator.db import init_db, create_project
from foodvideocreator.assets import import_asset
from foodvideocreator.runner import PipelineApp
from foodvideocreator.providers import MockAIProvider, MockVoiceProvider, MockImageProvider


def make_video(path):
    subprocess.run(["ffmpeg","-y","-f","lavfi","-i","testsrc2=size=180x320:rate=15:duration=1","-f","lavfi","-i","sine=frequency=330:duration=1","-c:v","libx264","-c:a","aac",str(path)],check=True,capture_output=True)


def test_external_render_stays_same_project_and_gets_video_gate(tmp_path):
    v=tmp_path/"done.mp4"; make_video(v)
    con=init_db(tmp_path/"job.db"); create_project(con,"p",None)
    import_asset(con,project_id="p",role="EXTERNAL_RENDER",path=v)
    app=PipelineApp(con=con,project_id="p",artifact_root=tmp_path/"a",contract_path="workflow/workflow_contract.yaml",ai_provider=MockAIProvider(),voice_provider=MockVoiceProvider(),image_provider=MockImageProvider())
    out=app.execute("IMPORT_EXISTING_VIDEO")
    assert out["result"]["machine_qa"]=="PASS"
    assert out["gate"]["gate_id"]
    app.approve_open_gate()
    assert app.status()["state"]["open_gate_id"] is None
