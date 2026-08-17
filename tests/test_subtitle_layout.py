from PIL import Image
from foodvideocreator.subtitles import layout_subtitle_cue, render_design_previews, evenly_time_texts, validate_cue_timing


def test_low_resolution_subtitle_layout_stays_safe(tmp_path):
    cues=evenly_time_texts(['これは低解像度でも二行以内に収める字幕です。','次の字幕です。'],2.0); frames=[]
    for i in range(3):
        p=tmp_path/f'f{i}.jpg'; Image.new('RGB',(240,426),(80+i*20,90,100)).save(p); frames.append(p)
    r=render_design_previews(frames,cues,tmp_path/'previews',width=240,height=426)
    assert r['result']=='PASS'; assert all(x['lines']<=2 for x in r['previews']); assert validate_cue_timing(cues,2.0)['result']=='PASS'; assert layout_subtitle_cue(cues[0]['text'],width=240,height=426)['result']=='PASS'
