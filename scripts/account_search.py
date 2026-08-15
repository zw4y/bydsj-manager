"""账号搜索工具函数（与 UI 解耦，便于单元测试）。"""

from __future__ import annotations


def find_account_rows(account_names: list[str], query: str) -> list[int]:
    """在游戏账号列表中精确查找，忽略大小写与首尾空格，返回 0 起始行号列表。"""
    target = query.strip().lower()
    if not target:
        return []
    return [
        index
        for index, name in enumerate(account_names)
        if name.strip().lower() == target
    ]


def format_search_log(query: str, matched_rows: list[int]) -> list[str]:
    """生成搜索结果日志文案；matched_rows 为 0 起始行号。"""
    target = query.strip()
    if not target:
        return ["搜索内容为空，请输入账号"]
    if not matched_rows:
        return [f'未匹配该账号"{target}"']
    return [
        f'已经搜索到账号"{target}"，目标在第 {row + 1} 行！'
        for row in matched_rows
    ]
