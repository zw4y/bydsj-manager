"""账号搜索功能的纯函数测试。"""

import pytest

from scripts.account_search import find_account_rows, format_search_log


def test_find_account_rows_exact_match():
    names = ["", "张三123", "李四", "王五"]
    assert find_account_rows(names, "张三123") == [1]


def test_find_account_rows_ignores_case_and_space():
    names = ["By881119", "by881119", "abc"]
    assert find_account_rows(names, "  BY881119 ") == [0, 1]


def test_find_account_rows_no_match():
    assert find_account_rows(["张三", "李四"], "王五") == []


def test_find_account_rows_empty_query():
    assert find_account_rows(["张三", "李四"], "   ") == []


def test_format_search_log_success():
    assert format_search_log("张三123", [16]) == [
        '已经搜索到账号"张三123"，目标在第 17 行！'
    ]


def test_format_search_log_multiple_matches():
    assert format_search_log("by881119", [0, 3]) == [
        '已经搜索到账号"by881119"，目标在第 1 行！',
        '已经搜索到账号"by881119"，目标在第 4 行！',
    ]


def test_format_search_log_failed():
    assert format_search_log("张三123", []) == ['未匹配该账号"张三123"']


def test_format_search_log_empty():
    assert format_search_log("   ", []) == ["搜索内容为空，请输入账号"]


def test_find_account_rows_requires_str_names():
    with pytest.raises(AttributeError):
        find_account_rows([None, "abc"], "abc")
