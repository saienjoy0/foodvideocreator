import subprocess
from PIL import Image
from foodvideocreator.media import append_thumbnail, ffprobe, verify_decode, audio_content_md5, compare_video_body


def make_normal(path,duration=1.2):
    subprocess.run(['ffmpeg','-y','-f','lavfi','-i',f'testsrc2=size=180x320:rate=30:duration={duration}','-f','lavfi','-i',f'sine=frequency=440:duration={duration}','-c:v','libx264','-pix_fmt','yuv420p','-c:a','aac',str(path)],check=True,capture_output=True)


def make_black_tail(path):
    subprocess.run(['ffmpeg','-y','-f','lavfi','-i','testsrc2=size=180x320:rate=30:duration=1.0','-f','lavfi','-i','color=c=black:size=180x320:rate=30:duration=0.2','-f','lavfi','-i','sine=frequency=440:duration=1.2','-filter_complex','[0:v][1:v]concat=n=2:v=1:a=0[v]','-map','[v]','-map','2:a','-c:v','libx264','-pix_fmt','yuv420p','-c:a','aac',str(path)],check=True,capture_output=True)


def thumb(path): Image.new('RGB',(1080,1920),(180,80,40)).save(path)


def test_final_normal_tail_appends_exact_frames_and_preserves_audio(tmp_path):
    src=tmp_path/'src.mp4'; t=tmp_path/'t.jpg'; out=tmp_path/'out.mp4'; make_normal(src); thumb(t)
    r=append_thumbnail(src,t,out)
    assert r['mode']=='append_0_1s' and r['thumbnail_frames']==3
    assert verify_decode(out)['result']=='PASS'
    assert audio_content_md5(src)==audio_content_md5(out)
    assert compare_video_body(src,out,tmp_path/'cmp')['result']=='PASS'


def test_final_black_tail_replaces_instead_of_appending(tmp_path):
    src=tmp_path/'src.mp4'; t=tmp_path/'t.jpg'; out=tmp_path/'out.mp4'; make_black_tail(src); thumb(t)
    r=append_thumbnail(src,t,out)
    assert r['mode']=='replace_black_tail'
    assert abs(ffprobe(out)['duration']-ffprobe(src)['duration'])<0.08
    assert audio_content_md5(src)==audio_content_md5(out)
    assert compare_video_body(src,out,tmp_path/'cmp',black_tail_start=r['black_tail_start'])['result']=='PASS'
