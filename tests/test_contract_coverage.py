import json
from pathlib import Path
from foodvideocreator.runner import STEP_PRIMARY_SLOT

ROOT=Path(__file__).resolve().parents[1]

def test_every_contract_step_has_runner_primary_slot():
    c=json.loads((ROOT/'workflow/workflow_contract.yaml').read_text())
    assert set(c['steps'])==set(STEP_PRIMARY_SLOT)


def test_every_blocking_check_has_implementation_reference():
    c=json.loads((ROOT/'workflow/workflow_contract.yaml').read_text())
    checks={x for s in c['steps'].values() for x in s['blocking_checks']}
    source='\n'.join(p.read_text(encoding='utf-8') for p in (ROOT/'foodvideocreator').rglob('*.py'))
    assert not [x for x in checks if x not in source]
