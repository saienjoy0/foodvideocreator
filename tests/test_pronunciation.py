import json
from pathlib import Path
from foodvideocreator.db import init_db,create_project
from foodvideocreator.directives import set_directive
from foodvideocreator.artifacts import write_json_artifact
from foodvideocreator.activities.script import run_script_final


def test_pronunciation_map_changes_spoken_not_display(tmp_path):
    con=init_db(tmp_path/'j.db');create_project(con,'p')
    cta=write_json_artifact(con,project_id='p',artifact_type='CTA_SCRIPT',slot='CTA_SCRIPT',artifact_root=tmp_path/'a',filename='cta.json',data={'text':'龍井蝦仁は中国の料理です。'})
    con.execute("UPDATE artifact_slots SET current_approved_id=? WHERE project_id='p' AND slot='CTA_SCRIPT'",(cta['artifact_id'],));con.commit()
    con.execute("INSERT INTO checks(project_id,check_type,artifact_id,artifact_sha256,measurement_json,result,blocking,rule_version) VALUES('p','CHECK_FACT_INTEGRITY',?,?, '{}','PASS',1,'v1')",(cta['artifact_id'],cta['sha256']));con.commit()
    set_directive(con,'p','PRONUNCIATION_MAP',{'龍井蝦仁':'ロンジンシャーレン'})
    out=run_script_final(con,project_id='p',artifact_root=tmp_path/'a',video_seconds=3,density_override=True)
    data=json.loads(Path(out['artifact']['path']).read_text())
    assert data['display_text']=='龍井蝦仁は中国の料理です。'
    assert data['spoken_text']=='ロンジンシャーレンは中国の料理です。'
