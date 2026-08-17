import subprocess
from PIL import Image
from foodvideocreator.assets import import_asset
from foodvideocreator.db import init_db, create_project
from foodvideocreator.directives import set_directive
from foodvideocreator.providers import MockAIProvider, MockVoiceProvider, MockImageProvider
from foodvideocreator.runner import PipelineApp


def make_video(path, duration=6):
    subprocess.run(["ffmpeg","-y","-f","lavfi","-i",f"testsrc2=size=240x426:rate=24:duration={duration}","-f","lavfi","-i",f"sine=frequency=300:duration={duration}","-c:v","libx264","-pix_fmt","yuv420p","-c:a","aac",str(path)],check=True,capture_output=True)


def ap(app,out):
    assert out["gate"] and not out["gate"].get("blocked_checks"); app.approve_open_gate()


def test_route_b_reaches_base_images(tmp_path):
    source=tmp_path/"source.mp4"; make_video(source)
    product=tmp_path/"product.jpg"; Image.new("RGB",(700,700),(220,180,120)).save(product)
    con=init_db(tmp_path/"job.db"); create_project(con,"p",None)
    import_asset(con,project_id="p",role="MAIN_SOURCE",path=source)
    import_asset(con,project_id="p",role="PRODUCT_IMAGE",path=product)
    app=PipelineApp(con=con,project_id="p",artifact_root=tmp_path/"artifacts",contract_path="workflow/workflow_contract.yaml",ai_provider=MockAIProvider(),voice_provider=MockVoiceProvider(),image_provider=MockImageProvider())
    ap(app,app.execute("VIDEO_ANALYSIS",source_path=source,dish_name="商品料理"))
    app.execute("RESEARCH_RANKING")
    ap(app,app.execute("SELECTION_CONFIRM",ranks=[1]))
    ap(app,app.execute("SCRIPT_DRAFT"))
    app.execute("TIPS")
    app.execute("ROUTE_SELECTION",route="B")
    out=app.execute("CTA"); assert out["result"]["density"]["result"]=="PASS"; ap(app,out)
    set_directive(con,"p","AUDIO_POLICY","NO_GENERATED_VOICE");set_directive(con,"p","BGM_POLICY","NONE")
    ap(app,app.execute("SCRIPT_FINAL"))
    ap(app,app.execute("PRODUCTION"))
    ap(app,app.execute("PUBLISHING_B"))
    ap(app,app.execute("BASE_COPY",product_info={"product_name":"商品料理","origin":"中国"}))
    out=app.execute("BASE_IMAGES"); ap(app,out)
    assert len(out["result"]["manifest"]["images"])==3
    out=app.execute("THUMBNAIL_BG",force_mode="B"); ap(app,out)
    out=app.execute("THUMBNAIL_TEXT",copy_lines=["中国の料理","まさか!?","意外な由来"]); ap(app,out)
    out=app.execute("FINAL")
    final=out["result"]["artifact"]
    from pathlib import Path
    from foodvideocreator.media import verify_decode
    assert Path(final["path"]).exists() and verify_decode(final["path"])["result"]=="PASS"
