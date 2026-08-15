"""从 Excel/剪贴板文本解析批量账号。"""

from __future__ import annotations


def parse_account_rows(text: str) -> tuple[list[dict], list[str]]:
    """解析剪贴板账号文本。

    返回 (合法行列表, 错误提示列表)。每行接受 1-5 个字段，按
    “账号 密码 二级密码 手机号 设备码”顺序填充，缺失字段默认空字符串；
    超过 5 个字段的行会被跳过并记录错误，不会中断其余行的导入。
    """
    field_keys = ["account", "password", "secondary_password", "phone", "device_code"]
    rows: list[dict] = []
    errors: list[str] = []
    for line_no, line in enumerate(text.splitlines(), 1):
        line = line.strip()
        if not line:
            continue
        parts = line.replace("\t", " ").split()
        if len(parts) > 5:
            errors.append(
                f"第 {line_no} 行字段数量为 {len(parts)}，最多 5 个：账号 密码 二级密码 手机号 设备码，已跳过"
            )
            continue
        row = {key: "" for key in field_keys}
        for index, key in enumerate(field_keys):
            if index < len(parts):
                row[key] = parts[index]
        rows.append(row)
    if not rows and not errors:
        raise ValueError("剪贴板中没有可导入的账号")
    return rows, errors


def filter_duplicate_accounts(
    rows: list[dict], existing_accounts: set[str]
) -> tuple[list[dict], list[str]]:
    """过滤已存在的账号，返回 (可导入行, 被跳过的账号名列表)。"""
    existing = set(existing_accounts)
    unique: list[dict] = []
    duplicates: list[str] = []
    for row in rows:
        if row["account"] in existing:
            duplicates.append(row["account"])
            continue
        existing.add(row["account"])
        unique.append(row)
    return unique, duplicates


def paste_target_rows(
    blank_flags: list[bool], anchor: int, count: int
) -> list[int]:
    """计算粘贴 N 行数据时的目标行位置。

    锚点为空白行时从该行开始填入；锚点为非空白行（账号行）时从锚点
    下一行开始填入，新账号排在原账号之后。优先填入连续空白行；空白行
    不够时，剩余行补插在最后一个空白行之后。
    """
    start = (
        anchor
        if anchor < len(blank_flags) and blank_flags[anchor]
        else anchor + 1
    )
    targets: list[int] = []
    pos = start
    while len(targets) < count and pos < len(blank_flags) and blank_flags[pos]:
        targets.append(pos)
        pos += 1
    remaining = count - len(targets)
    if remaining:
        targets.extend(range(pos, pos + remaining))
    return targets


def build_tsv(rows: list[list[str]]) -> str:
    """把行矩阵拼成 Tab 分隔文本，空单元格保留为空串。"""
    return "\n".join("\t".join(row) for row in rows)
