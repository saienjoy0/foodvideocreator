from foodvideocreator.checks import dish_identity_result


def test_below_threshold_blocks():
    assert dish_identity_result(0.79, False) == "NEEDS_USER_CONFIRMATION"


def test_threshold_passes_without_conflict():
    assert dish_identity_result(0.80, False) == "PASS"


def test_conflict_blocks_even_high_confidence():
    assert dish_identity_result(0.99, True) == "NEEDS_USER_CONFIRMATION"
