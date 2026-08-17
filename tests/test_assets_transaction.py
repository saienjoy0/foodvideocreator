import pytest
from foodvideocreator.db import init_db, create_project, get_workflow_revision
from foodvideocreator.assets import import_asset


def test_main_source_change_rejected_without_partial_insert(tmp_path):
    a=tmp_path/'a.bin'; b=tmp_path/'b.bin'; a.write_bytes(b'a'); b.write_bytes(b'b')
    con=init_db(tmp_path/'job.db'); create_project(con,'p')
    import_asset(con,project_id='p',role='MAIN_SOURCE',path=a)
    rev=get_workflow_revision(con,'p'); count=con.execute("select count(*) from assets where project_id='p'").fetchone()[0]
    with pytest.raises(RuntimeError,match='NEW_PROJECT_REQUIRED'):
        import_asset(con,project_id='p',role='MAIN_SOURCE',path=b)
    assert con.execute("select count(*) from assets where project_id='p'").fetchone()[0]==count
    assert get_workflow_revision(con,'p')==rev


def test_same_main_source_does_not_bump_revision_again(tmp_path):
    a=tmp_path/'a.bin'; a.write_bytes(b'a')
    con=init_db(tmp_path/'job.db'); create_project(con,'p')
    import_asset(con,project_id='p',role='MAIN_SOURCE',path=a); rev=get_workflow_revision(con,'p')
    import_asset(con,project_id='p',role='MAIN_SOURCE',path=a)
    assert get_workflow_revision(con,'p')==rev
