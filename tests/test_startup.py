from pathlib import Path
from foodvideocreator.startup import validate_startup
from foodvideocreator.db import init_db, create_project
from foodvideocreator.directives import set_directive


def test_startup_passes_current_bundle(tmp_path):
    con=init_db(tmp_path/'job.db'); create_project(con,'p')
    r=validate_startup(contract_path='workflow/workflow_contract.yaml',rules_dir='rules/v4',con=con,project_id='p',assets_dir=tmp_path/'assets'); assert r['result']=='PASS'


def test_startup_detects_legacy_thumbnail_conflict(tmp_path):
    rules=tmp_path/'rules'; rules.mkdir()
    for p in Path('rules/v4').glob('*.txt'): (rules/p.name).write_text(p.read_text(encoding='utf-8'),encoding='utf-8')
    (rules/'13_Shortsサムネ.txt').write_text('legacy',encoding='utf-8')
    r=validate_startup(contract_path='workflow/workflow_contract.yaml',rules_dir=rules); assert r['result']=='FAIL'
    assert any(c['name']=='legacy_thumbnail_conflict' and c['result']=='FAIL' for c in r['checks'])


def test_fixed_bgm_is_conditional(tmp_path):
    con=init_db(tmp_path/'job.db'); create_project(con,'p'); assets=tmp_path/'assets'; assets.mkdir()
    assert validate_startup(contract_path='workflow/workflow_contract.yaml',rules_dir='rules/v4',con=con,project_id='p',assets_dir=assets)['result']=='PASS'
    set_directive(con,'p','BGM_POLICY','FIXED'); (assets/'fixed_bgm.MP3').write_bytes(b'test-private-asset')
    r=validate_startup(contract_path='workflow/workflow_contract.yaml',rules_dir='rules/v4',con=con,project_id='p',assets_dir=assets); assert r['result']=='PASS'
