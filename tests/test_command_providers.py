import sys
from pathlib import Path
from PIL import Image

from foodvideocreator.providers.command import CommandJSONProvider,CommandVoiceProvider,CommandImageProvider

ROOT=Path(__file__).resolve().parents[1]


def test_command_ai_provider_roundtrip():
    p=CommandJSONProvider([sys.executable,str(ROOT/'examples/mock_ai_command.py')])
    out=p.video_semantic_analysis({'dish_name':'外部テスト','video_info':{'duration':2}})
    assert out['dish_identity']=='外部テスト' and out['dish_identity_confidence']>=.8


def test_command_voice_provider_writes_real_file(tmp_path):
    p=CommandVoiceProvider([sys.executable,str(ROOT/'examples/mock_voice_command.py')])
    outpath=tmp_path/'v.wav'
    out=p.synthesize('テスト音声',outpath,{'chars_per_second':10})
    assert outpath.exists() and outpath.stat().st_size>44 and out['duration']>0


def test_command_image_provider_writes_real_file(tmp_path):
    src=tmp_path/'src.jpg';Image.new('RGB',(80,120),'white').save(src)
    outpath=tmp_path/'out.jpg'
    p=CommandImageProvider([sys.executable,str(ROOT/'examples/mock_image_command.py')])
    out=p.reconstruct_food_background(src,outpath,{'no_text':True})
    assert outpath.exists() and Image.open(outpath).size==(1080,1920)
