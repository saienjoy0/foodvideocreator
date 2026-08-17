from foodvideocreator.rules import load_rule_bundle


def test_step_rules_are_loaded_in_full():
    b=load_rule_bundle("rules/v4","VIDEO_ANALYSIS")
    assert len(b["files"])==2
    assert "工程2：動画理解・分析" in b["text"]
    assert "工程1：人気グルメShorts固定原則" in b["text"]
    assert len(b["sha256"])==64


def test_route_specific_rule():
    assert "工程7A" in load_rule_bundle("rules/v4","CTA",route="A")["text"]
    assert "工程7B" in load_rule_bundle("rules/v4","CTA",route="B")["text"]
