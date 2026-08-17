from foodvideocreator.commands import parse_command


def test_command_contract():
    assert parse_command("OK")["intent"] == "APPROVE"
    assert parse_command("1位")["ranks"] == [1]
    assert parse_command("1と3")["ranks"] == [1, 3]
    assert parse_command("誘導しなくていい") == {"intent":"ROUTE","route":"A","cta_none":True}
    assert parse_command("BGMなし")["value"] == "NONE"
    assert parse_command("文字入れて")["intent"] == "THUMBNAIL_TEXT"
