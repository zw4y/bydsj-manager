"""批量改密用的密码生成与校验。"""

from __future__ import annotations

import random
import re
import string

MIN_LEN = 6
MAX_LEN = 16


def validate_password(password: str) -> bool:
    return MIN_LEN <= len(password) <= MAX_LEN and re.fullmatch(r"[A-Za-z0-9]+", password) is not None


def generate_password(letter_count: int, digit_count: int, letters_first: bool = True) -> str:
    total = letter_count + digit_count
    if not MIN_LEN <= total <= MAX_LEN:
        raise ValueError(f"密码总长度必须为 {MIN_LEN}-{MAX_LEN} 位，当前为 {total} 位")
    if letter_count < 0 or digit_count < 0:
        raise ValueError("字母位数和数字位数不能为负数")
    letters = "".join(random.choice(string.ascii_lowercase) for _ in range(letter_count))
    digits = "".join(random.choice(string.digits) for _ in range(digit_count))
    return letters + digits if letters_first else digits + letters
