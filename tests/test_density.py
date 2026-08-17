from foodvideocreator.checks import effective_char_count, density_bounds, density_result


def test_effective_count_ignores_space_punctuation_brackets():
    assert effective_char_count("龍井蝦仁（ロンジン）！ 123") == len("龍井蝦仁ロンジン123")


def test_density_bound_example():
    assert density_bounds(61.6) == (493, 554)


def test_density_fail_and_override():
    assert density_result("短い", 10)["result"] == "FAIL"
    assert density_result("短い", 10, override=True)["result"] == "PASS"
