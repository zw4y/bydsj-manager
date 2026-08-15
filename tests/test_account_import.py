import pytest

from scripts.account_import import (
    build_tsv,
    filter_duplicate_accounts,
    parse_account_rows,
    paste_target_rows,
)


def test_parse_single_row_with_spaces():
    rows, errors = parse_account_rows(
        "by881119 uj3858 z878678 13357878267 157bc3df28f459f0"
    )
    assert len(rows) == 1
    assert errors == []
    assert rows[0]["account"] == "by881119"
    assert rows[0]["password"] == "uj3858"
    assert rows[0]["secondary_password"] == "z878678"
    assert rows[0]["phone"] == "13357878267"
    assert rows[0]["device_code"] == "157bc3df28f459f0"


def test_parse_multiple_rows_and_tabs():
    text = "a\t1\t2\t3\t4\nb 5 6 7 8"
    rows, errors = parse_account_rows(text)
    assert len(rows) == 2
    assert errors == []
    assert rows[1]["account"] == "b"


def test_parse_partial_fields_fills_missing():
    rows, errors = parse_account_rows(
        "onlyaccount\n"
        "account2 pwd2\n"
        "account3 pwd3 sec3\n"
        "account4 pwd4 sec4 13300000000\n"
        "account5 pwd5 sec5 13300000000 d5"
    )
    assert errors == []
    assert len(rows) == 5
    assert rows[0] == {
        "account": "onlyaccount",
        "password": "",
        "secondary_password": "",
        "phone": "",
        "device_code": "",
    }
    assert rows[1] == {
        "account": "account2",
        "password": "pwd2",
        "secondary_password": "",
        "phone": "",
        "device_code": "",
    }
    assert rows[2]["secondary_password"] == "sec3"
    assert rows[3]["phone"] == "13300000000"
    assert rows[4]["device_code"] == "d5"


def test_parse_too_many_fields_skips_with_error():
    rows, errors = parse_account_rows(
        "good 1 2 3 4\nbad 1 2 3 4 5 6"
    )
    assert len(rows) == 1
    assert len(errors) == 1
    assert "第 2 行" in errors[0]
    assert "最多 5 个" in errors[0]


def test_parse_all_rows_wrong_still_reports_errors():
    rows, errors = parse_account_rows("a 1 2 3 4 5\nb 6 7 8 9 10 11")
    assert rows == []
    assert len(errors) == 2


def test_parse_empty_raises():
    with pytest.raises(ValueError, match="没有可导入"):
        parse_account_rows("\n\n")


def test_filter_duplicate_accounts_skips_existing_and_inner_duplicates():
    rows = [
        {"account": "a", "password": "1"},
        {"account": "b", "password": "2"},
        {"account": "a", "password": "3"},
    ]
    unique, duplicates = filter_duplicate_accounts(rows, {"a"})
    assert [row["account"] for row in unique] == ["b"]
    assert duplicates == ["a", "a"]


def test_filter_duplicate_accounts_no_duplicates():
    rows = [
        {"account": "a", "password": "1"},
        {"account": "b", "password": "2"},
    ]
    unique, duplicates = filter_duplicate_accounts(rows, set())
    assert [row["account"] for row in unique] == ["a", "b"]
    assert duplicates == []


def test_build_tsv_rectangular_rows():
    assert build_tsv([["a", "b"], ["c", "d"]]) == "a\tb\nc\td"


def test_build_tsv_preserves_empty_cells():
    assert build_tsv([["", "x"], ["y", ""]]) == "\tx\ny\t"


def test_paste_target_fills_consecutive_blanks():
    flags = [False, False, True, True, True, False]
    assert paste_target_rows(flags, 2, 2) == [2, 3]


def test_paste_target_inserts_extra_after_blanks():
    flags = [False, False, True, True, True, False]
    assert paste_target_rows(flags, 2, 5) == [2, 3, 4, 5, 6]


def test_paste_target_non_blank_anchor_inserts_below():
    flags = [False, False, True, True, False]
    assert paste_target_rows(flags, 1, 3) == [2, 3, 4]


def test_paste_target_non_blank_anchor_at_end_appends():
    flags = [False, False]
    assert paste_target_rows(flags, 1, 3) == [2, 3, 4]


def test_paste_target_blank_run_to_end_appends():
    flags = [False, True, True]
    assert paste_target_rows(flags, 1, 4) == [1, 2, 3, 4]
