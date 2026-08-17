from foodvideocreator.commands import parse_command
from foodvideocreator.editorial import (
    attention_segments_result,
    compose_spoken_text,
    core_promise_result,
    editorial_greenlight_result,
    hook_package_result,
    segment_density_result,
)


def test_attention_is_canonical_and_covers_full_video():
    r=attention_segments_result([
        {"segment_id":"a","start_sec":0,"end_sec":2,"mode":"VISUAL_ONLY","reason":"visual","evidence_scene_ids":["s1"]},
        {"segment_id":"b","start_sec":2,"end_sec":10,"mode":"NARRATION_REQUIRED","reason":"context","evidence_scene_ids":["s2"]},
    ],10,{"s1","s2"})
    assert r["result"]=="PASS"


def test_greenlight_numeric_score_cannot_override_no():
    p={"q1":{"answer":True,"reason":"x","evidence_ids":["c1"]},"q2":{"answer":False,"reason":"x","evidence_ids":["s1"]},"q3":{"answer":True,"reason":"x","evidence_ids":["c1"]},"score":99}
    r=editorial_greenlight_result(p,{"c1","s1"})
    assert r["decision"]=="REWORK" and r["result"]=="FAIL"


def test_explicit_override_is_recorded_not_silent():
    p={"q1":{"answer":False,"reason":"x","evidence_ids":["c1"]},"q2":{"answer":False,"reason":"x","evidence_ids":["s1"]},"q3":{"answer":True,"reason":"x","evidence_ids":["c1"]}}
    r=editorial_greenlight_result(p,{"c1","s1"},override=True)
    assert r["decision"]=="KILL_RECOMMEND" and r["result"]=="PASS" and r["override"] is True


def test_ok_is_not_editorial_override():
    assert parse_command("OK")["intent"]=="APPROVE"
    assert parse_command("それでも進めて")["intent"]=="EDITORIAL_OVERRIDE"


def test_core_promise_uses_only_selected_claims():
    assert core_promise_result("ただの白菜に見えて実は高級料理",["c1"],{"c1"})["result"]=="PASS"
    assert core_promise_result("x",["c2"],{"c1"})["result"]=="FAIL"


def test_no_text_hook_is_valid_formal_candidate():
    p={"hook_id":"h1","visual_start_sec":0,"visual_end_sec":2.5,"visual_scene_ids":["s1"],"subtitle_text":"","spoken_text":"","audio_strategy":"ORIGINAL_ASMR","no_text":True,"promise":"texture","payoff_claim_ids":["c1"],"critics":{"viewer":{"pass":True},"shorts_editor":{"pass":True},"fact":{"pass":True},"procedure":{"pass":True}}}
    assert hook_package_result(p,{"s1"},{"c1"})["result"]=="PASS"


def test_segment_density_uses_analysis_windows_not_provider_windows():
    attn=[
        {"segment_id":"a","start_sec":0,"end_sec":10,"mode":"NARRATION_REQUIRED"},
        {"segment_id":"b","start_sec":10,"end_sec":20,"mode":"VISUAL_ONLY"},
    ]
    texts=[{"segment_id":"a","text":"豆"*82},{"segment_id":"b","text":""}]
    r=segment_density_result(attn,texts,full_text="豆"*82)
    assert r["density_min"]==80 and r["density_max"]==90 and r["result"]=="PASS"


def test_missing_analysis_segment_cannot_lower_density_requirement():
    attn=[{"segment_id":"a","start_sec":0,"end_sec":10,"mode":"NARRATION_REQUIRED"},{"segment_id":"b","start_sec":10,"end_sec":20,"mode":"VISUAL_ONLY"}]
    r=segment_density_result(attn,[{"segment_id":"a","text":"豆"*82}],full_text="豆"*82)
    assert r["density_qa"]=="FAIL_MISSING_SEGMENT_TEXT"


def test_hook_overlay_is_separate_from_silent_segment_text():
    attn=[{"segment_id":"a","start_sec":0,"end_sec":10,"mode":"NARRATION_REQUIRED"},{"segment_id":"b","start_sec":10,"end_sec":20,"mode":"VISUAL_ONLY"}]
    hook={"no_text":False,"subtitle_text":"これ豆腐!?","spoken_text":"","audio_strategy":"ORIGINAL"}
    texts=[{"segment_id":"a","text":"豆"*82},{"segment_id":"b","text":""}]
    r=segment_density_result(attn,texts,full_text="これ豆腐!?"+"豆"*82,selected_hook=hook)
    assert r["result"]=="PASS" and r["hook_effective_chars_excluded"]==4
    assert compose_spoken_text(attn,texts,hook)=="豆"*82
