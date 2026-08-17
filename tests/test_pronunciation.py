import json
from pathlib import Path
from foodvideocreator.db import init_db,create_project
from foodvideocreator.directives import set_directive
from foodvideocreator.artifacts import write_json_artifact
from foodvideocreator.activities.script import run_script_final


def test_pronunciation_map_changes_spoken_not_display(tmp_path):
    con=init_db(tmp_path/'j.db');create_project(con,'p')
    text='龍井蝦仁は中国の料理です。'
    analysis=write_json_artifact(
        con,project_id='p',artifact_type='ANALYSIS',slot='ANALYSIS',artifact_root=tmp_path/'a',filename='analysis.json',
        data={
            'major_scenes':[{'scene_id':'scene_01','start':0.0,'end':3.0,'description':'料理'}],
            'attention_segments':[{'segment_id':'attn_01','start_sec':0.0,'end_sec':3.0,'mode':'NARRATION_REQUIRED','reason':'発音テスト','evidence_scene_ids':['scene_01']}],
        },
    )
    con.execute("UPDATE artifact_slots SET current_approved_id=? WHERE project_id='p' AND slot='ANALYSIS'",(analysis['artifact_id'],))
    cta=write_json_artifact(
        con,project_id='p',artifact_type='CTA_SCRIPT',slot='CTA_SCRIPT',artifact_root=tmp_path/'a',filename='cta.json',
        data={'text':text,'display_text':text,'segment_texts':[{'segment_id':'attn_01','text':text}],'selected_hook':None},
    )
    con.execute("UPDATE artifact_slots SET current_approved_id=? WHERE project_id='p' AND slot='CTA_SCRIPT'",(cta['artifact_id'],));con.commit()
    con.execute("INSERT INTO checks(project_id,check_type,artifact_id,artifact_sha256,measurement_json,result,blocking,rule_version) VALUES('p','CHECK_FACT_INTEGRITY',?,?, '{}','PASS',1,'v1')",(cta['artifact_id'],cta['sha256']));con.commit()
    set_directive(con,'p','PRONUNCIATION_MAP',{'龍井蝦仁':'ロンジンシャーレン'})
    out=run_script_final(con,project_id='p',artifact_root=tmp_path/'a',video_seconds=3,density_override=True)
    data=json.loads(Path(out['artifact']['path']).read_text())
    assert data['display_text']==text
    assert data['spoken_text']=='ロンジンシャーレンは中国の料理です。'
