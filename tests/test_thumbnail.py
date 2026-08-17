from PIL import Image
from foodvideocreator.fonts import find_font_face, TARGET_FULL_NAME
from foodvideocreator.thumbnail import compose_thumbnail_text


def test_exact_font_face_and_thumbnail_bbox(tmp_path):
    path, idx = find_font_face(); assert path.exists(); assert idx is not None
    bg=tmp_path/"bg.jpg"; Image.new("RGB",(1080,1920),(170,120,80)).save(bg)
    out=tmp_path/"thumb.jpg"; prev=tmp_path/"prev.jpg"; r=compose_thumbnail_text(bg,["中国の料理","まさか!?","意外な由来"],out,prev)
    assert r["font_name"] == TARGET_FULL_NAME; assert r["real_font_composite"] is True; assert Image.open(out).size == (1080,1920); assert Image.open(prev).size == (270,480)
    for line in r["lines"]:
        x1,y1,x2,y2=line["bbox"]; assert 162 <= x1 <= x2 <= 918; assert 480 <= y1 <= y2 <= 1440; assert .55 <= line["horizontal_scale"] <= 1.0
