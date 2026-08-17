import subprocess
from foodvideocreator.media import ffprobe, verify_decode, final_thumbnail_frames


def make_video(path, duration=2):
    subprocess.run(["ffmpeg","-y","-f","lavfi","-i",f"testsrc2=size=180x320:rate=30:duration={duration}","-f","lavfi","-i",f"sine=frequency=440:duration={duration}","-c:v","libx264","-pix_fmt","yuv420p","-c:a","aac",str(path)],check=True,capture_output=True)


def test_probe_and_decode(tmp_path):
    p=tmp_path/"v.mp4"; make_video(p)
    info=ffprobe(p)
    assert info["width"]==180 and info["height"]==320
    assert abs(info["fps"]-30)<.01
    assert info["audio_present"] is True
    assert verify_decode(p)["result"]=="PASS"
    assert final_thumbnail_frames(30)==3
    assert final_thumbnail_frames(59.94)==6
