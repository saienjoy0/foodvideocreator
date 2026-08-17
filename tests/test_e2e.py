import subprocess
from pathlib import Path

from foodvideocreator.assets import import_asset
from foodvideocreator.db import init_db, create_project
from foodvideocreator.directives import set_directive
from foodvideocreator.providers import MockAIProvider, MockVoiceProvider, MockImageProvider
from foodvideocreator.runner import PipelineApp
from foodvideocreator.media import ffprobe, verify_decode


def make_video(path, duration=6):
    subprocess.run(["ffmpeg","-y","-f","lavfi","-i",f"testsrc2=size=360x640:rate=30:duration={duration}","-f","lavfi","-i",f"sine=frequency=330:duration={duration}","-c:v","libx264","-pix_fmt","yuv420p","-c:a","aac",str(path)],check=True,capture_output=True)


def approve(app, out):
    g=out["gate"]
    assert g and not g.get("blocked_checks")
    return app.approve_open_gate()


def test_full_route_a_e2e(tmp_path):
    source=tmp_path/"source.mp4"; make_video(source)
    con=init_db(tmp_path/"job.db"); create_project(con,"p1",None)
    import_asset(con,project_id="p1",role="MAIN_SOURCE",path=source)
    app=PipelineApp(con=con,project_id="p1",artifact_root=tmp_path/"artifacts",contract_path="workflow/workflow_contract.yaml",ai_provider=MockAIProvider(),voice_provider=MockVoiceProvider(),image_provider=MockImageProvider())
    out=app.execute("VIDEO_ANALYSIS",source_path=source,dish_name="テスト料理"); approve(app,out)
    out=app.execute("RESEARCH_RANKING"); assert out["gate"] is None
    out=app.execute("SELECTION_CONFIRM",ranks=[1],video_seconds=6); approve(app,out)
    out=app.execute("SCRIPT_DRAFT",video_seconds=6); assert out["result"]["density"]["result"]=="PASS"; approve(app,out)
    out=app.execute("TIPS",video_seconds=6); assert out["result"]["density"]["result"]=="PASS"
    app.execute("ROUTE_SELECTION",route="A")
    out=app.execute("CTA",cta_none=True); approve(app,out)
    set_directive(con,"p1","AUDIO_POLICY","NO_GENERATED_VOICE")
    set_directive(con,"p1","BGM_POLICY","NONE")
    out=app.execute("SCRIPT_FINAL",video_seconds=6); assert out["result"]["density"]["result"]=="PASS"; approve(app,out)
    out=app.execute("PRODUCTION"); assert out["result"]["machine_qa"]=="PASS"; approve(app,out)
    out=app.execute("PUBLISHING_A"); approve(app,out)
    out=app.execute("THUMBNAIL_BG",force_mode="B"); assert out["result"]["qa"]=="PASS"; approve(app,out)
    out=app.execute("THUMBNAIL_TEXT",copy_lines=["中国の料理","まさか!?","意外な由来"]); approve(app,out)
    out=app.execute("FINAL")
    final=out["result"]["artifact"]
    assert Path(final["path"]).exists()
    assert verify_decode(final["path"])["result"]=="PASS"
    info=ffprobe(final["path"])
    assert info["duration"] >= 6
