from foodvideocreator.db import init_db,create_project
from foodvideocreator.directives import set_directive
from foodvideocreator.activities.production import _bgm_config


def test_fixed_bgm_can_use_global_asset_without_per_project_import(tmp_path):
    assets=tmp_path/'assets';assets.mkdir();p=assets/'fixed_bgm.MP3';p.write_bytes(b'ID3test')
    con=init_db(tmp_path/'j.db');create_project(con,'p');set_directive(con,'p','BGM_POLICY','FIXED')
    path,vol=_bgm_config(con,'p',assets)
    assert path==str(p) and vol==0.5

import pytest

def test_missing_asmr_asset_blocks(tmp_path):
    con=init_db(tmp_path/'a.db');create_project(con,'a');set_directive(con,'a','BGM_POLICY','ASMR')
    with pytest.raises(RuntimeError,match='ASMR_BGM_ASSET_REQUIRED'):
        _bgm_config(con,'a',tmp_path/'assets')
