from foodvideocreator.contract import load_contract, validate_contract, REQUIRED_STEPS


def test_contract_is_complete():
    contract = load_contract("workflow/workflow_contract.yaml")
    validate_contract(contract)
    assert set(contract["steps"]) == REQUIRED_STEPS


def test_external_render_route_exists():
    contract = load_contract("workflow/workflow_contract.yaml")
    step = contract["steps"]["IMPORT_EXISTING_VIDEO"]
    assert step["data_dependencies"] == ["EXTERNAL_RENDER"]
    assert step["opens_gate"] == "IMPORTED_VIDEO_APPROVAL"
