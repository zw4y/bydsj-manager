"""本机按卡密隔离的加密游戏账号存储。"""

from __future__ import annotations

import base64
import os
import sqlite3
from datetime import datetime

from cryptography.hazmat.primitives.ciphers.aead import AESGCM


class LocalAccountStore:
    def __init__(self, db_path: str, key: bytes):
        if len(key) != 32:
            raise ValueError("key must be 32 bytes")
        self._db_path = db_path
        self._key = key
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self._db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS accounts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    account TEXT UNIQUE NOT NULL,
                    enc_password TEXT NOT NULL,
                    enc_secondary_password TEXT NOT NULL,
                    login_type TEXT NOT NULL,
                    cached_user_id INTEGER,
                    nickname TEXT,
                    device_code TEXT NOT NULL DEFAULT '',
                    phone TEXT NOT NULL DEFAULT '',
                    total_infull_num INTEGER NOT NULL DEFAULT 0,
                    cannon INTEGER NOT NULL DEFAULT 0,
                    sort_order INTEGER NOT NULL DEFAULT 0,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """
            )
        columns = [row[1] for row in conn.execute("PRAGMA table_info(accounts)").fetchall()]
        if "device_code" not in columns:
            conn.execute("ALTER TABLE accounts ADD COLUMN device_code TEXT NOT NULL DEFAULT ''")
        if "phone" not in columns:
            conn.execute("ALTER TABLE accounts ADD COLUMN phone TEXT NOT NULL DEFAULT ''")
        if "total_infull_num" not in columns:
            conn.execute("ALTER TABLE accounts ADD COLUMN total_infull_num INTEGER NOT NULL DEFAULT 0")
        if "cannon" not in columns:
            conn.execute("ALTER TABLE accounts ADD COLUMN cannon INTEGER NOT NULL DEFAULT 0")
        if "sort_order" not in columns:
            conn.execute("ALTER TABLE accounts ADD COLUMN sort_order INTEGER NOT NULL DEFAULT 0")

    def _encrypt(self, plaintext: str) -> str:
        nonce = os.urandom(12)
        ciphertext = AESGCM(self._key).encrypt(nonce, plaintext.encode("utf-8"), None)
        return base64.b64encode(nonce + ciphertext).decode("ascii")

    def _decrypt(self, blob: str) -> str:
        raw = base64.b64decode(blob)
        nonce, ciphertext = raw[:12], raw[12:]
        return AESGCM(self._key).decrypt(nonce, ciphertext, None).decode("utf-8")

    def add_account(
        self,
        account: str,
        password: str,
        secondary_password: str,
        login_type: str,
        cached_user_id: int | None = None,
        nickname: str | None = None,
        device_code: str = "",
        phone: str = "",
        total_infull_num: int = 0,
        cannon: int = 0,
        sort_order: int | None = None,
    ) -> dict:
        now = datetime.now().isoformat(timespec="seconds")
        enc_pwd = self._encrypt(password)
        enc_sec = self._encrypt(secondary_password or "")
        with self._connect() as conn:
            if sort_order is None:
                sort_order = conn.execute(
                    "SELECT COALESCE(MAX(sort_order), -1) + 1 FROM accounts"
                ).fetchone()[0]
            cur = conn.execute(
                """
                INSERT INTO accounts(account, enc_password, enc_secondary_password, login_type,
                                     cached_user_id, nickname, device_code, phone, total_infull_num,
                                     cannon, sort_order, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(account) DO UPDATE SET
                    enc_password = excluded.enc_password,
                    enc_secondary_password = excluded.enc_secondary_password,
                    login_type = excluded.login_type,
                    cached_user_id = excluded.cached_user_id,
                    nickname = excluded.nickname,
                    device_code = excluded.device_code,
                    phone = excluded.phone,
                    total_infull_num = excluded.total_infull_num,
                    cannon = excluded.cannon,
                    sort_order = accounts.sort_order,
                    updated_at = excluded.updated_at
                """,
                (
                    account,
                    enc_pwd,
                    enc_sec,
                    login_type,
                    cached_user_id,
                    nickname,
                    device_code or "",
                    phone or "",
                    total_infull_num or 0,
                    cannon or 0,
                    sort_order,
                    now,
                    now,
                ),
            )
            row = conn.execute("SELECT * FROM accounts WHERE account = ?", (account,)).fetchone()
        return dict(row)

    def list_accounts(self) -> list[dict]:
        with self._connect() as conn:
            rows = conn.execute("SELECT * FROM accounts ORDER BY sort_order, id").fetchall()
        result = []
        for row in rows:
            item = dict(row)
            item["password"] = self._decrypt(item.pop("enc_password"))
            item["secondary_password"] = self._decrypt(item.pop("enc_secondary_password"))
            result.append(item)
        return result

    def renumber_accounts(self, ordered_ids: list[int]) -> None:
        """按给定 id 顺序把 sort_order 重排为 0,1,2...，原子写入。"""
        now = datetime.now().isoformat(timespec="seconds")
        with self._connect() as conn:
            for index, account_id in enumerate(ordered_ids):
                conn.execute(
                    "UPDATE accounts SET sort_order = ?, updated_at = ? WHERE id = ?",
                    (index, now, account_id),
                )

    def get_account(self, account_id: int) -> dict | None:
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM accounts WHERE id = ?", (account_id,)).fetchone()
        if not row:
            return None
        item = dict(row)
        item["password"] = self._decrypt(item.pop("enc_password"))
        item["secondary_password"] = self._decrypt(item.pop("enc_secondary_password"))
        return item

    def update_account(
        self,
        account_id: int,
        password: str,
        secondary_password: str,
        device_code: str | None = None,
        phone: str | None = None,
        nickname: str | None = None,
        total_infull_num: int | None = None,
        account: str | None = None,
        cannon: int | None = None,
    ) -> None:
        now = datetime.now().isoformat(timespec="seconds")
        with self._connect() as conn:
            conn.execute(
                """
                UPDATE accounts
                SET account = COALESCE(?, account),
                    enc_password = ?,
                    enc_secondary_password = ?,
                    device_code = COALESCE(?, device_code),
                    phone = COALESCE(?, phone),
                    nickname = COALESCE(?, nickname),
                    total_infull_num = COALESCE(?, total_infull_num),
                    cannon = COALESCE(?, cannon),
                    updated_at = ?
                WHERE id = ?
                """,
                (
                    account,
                    self._encrypt(password),
                    self._encrypt(secondary_password or ""),
                    device_code,
                    phone,
                    nickname,
                    total_infull_num,
                    cannon,
                    now,
                    account_id,
                ),
            )

    def delete_account(self, account_id: int) -> None:
        with self._connect() as conn:
            conn.execute("DELETE FROM accounts WHERE id = ?", (account_id,))
            rows = conn.execute("SELECT id FROM accounts ORDER BY sort_order, id").fetchall()
            for index, row in enumerate(rows):
                conn.execute(
                    "UPDATE accounts SET sort_order = ? WHERE id = ?",
                    (index, row["id"]),
                )
