import os
import sqlite3

import pytest

from scripts.local_store import LocalAccountStore


KEY = bytes(range(32))


@pytest.fixture()
def store(tmp_path):
    return LocalAccountStore(str(tmp_path / "accounts.db"), KEY)


def test_add_and_list_returns_plaintext_passwords(store):
    store.add_account("wzj1004232242", "zf6114", "sec123", "passport", 401240258, "nick")
    items = store.list_accounts()
    assert len(items) == 1
    assert items[0]["account"] == "wzj1004232242"
    assert items[0]["password"] == "zf6114"
    assert items[0]["secondary_password"] == "sec123"
    assert items[0]["login_type"] == "passport"
    assert items[0]["cached_user_id"] == 401240258


def test_update_password_persists(store):
    row = store.add_account("wzj1004232242", "old", "", "passport")
    store.update_account(row["id"], password="new", secondary_password="sec")
    item = store.list_accounts()[0]
    assert item["password"] == "new"
    assert item["secondary_password"] == "sec"


def test_delete_removes_account(store):
    row = store.add_account("wzj1004232242", "pwd", "", "passport")
    store.delete_account(row["id"])
    assert store.list_accounts() == []


def test_add_blank_row_persists_with_is_blank(store):
    row = store.add_blank_row()
    items = store.list_accounts()
    assert len(items) == 1
    assert items[0]["is_blank"] == 1
    assert items[0]["account"].startswith("__blank__")
    assert items[0]["password"] == ""
    # 合成账号唯一，可加多行
    row2 = store.add_blank_row()
    assert row["id"] != row2["id"]
    assert len({a["account"] for a in store.list_accounts()}) == 2


def test_blank_row_convert_to_account(store):
    blank = store.add_blank_row()
    store.update_account(
        blank["id"],
        "pwd1",
        "sec1",
        None,
        None,
        None,
        None,
        "真实账号",
        0,
        is_blank=0,
    )
    items = store.list_accounts()
    assert len(items) == 1
    assert items[0]["is_blank"] == 0
    assert items[0]["account"] == "真实账号"
    assert items[0]["password"] == "pwd1"


def test_blank_row_saves_fields_without_account(store):
    blank = store.add_blank_row()
    store.update_account(
        blank["id"],
        "pwd9",
        "",
        None,
        None,
        None,
        None,
        None,
        0,
        is_blank=1,
    )
    items = store.list_accounts()
    assert items[0]["is_blank"] == 1
    assert items[0]["account"].startswith("__blank__")
    assert items[0]["password"] == "pwd9"


def test_blank_row_deleted_by_id(store):
    blank = store.add_blank_row()
    store.delete_account(blank["id"])
    assert store.list_accounts() == []


def test_blank_row_order_via_renumber(store):
    a = store.add_account("账号A", "p", "", "passport")
    b = store.add_blank_row()
    c = store.add_account("账号C", "p", "", "passport")
    store.renumber_accounts([b["id"], a["id"], c["id"]])
    items = store.list_accounts()
    assert [x["id"] for x in items] == [b["id"], a["id"], c["id"]]


def test_db_file_contains_no_plaintext_password(tmp_path):
    db_path = tmp_path / "accounts.db"
    LocalAccountStore(str(db_path), KEY).add_account("wzj1004232242", "zf6114", "SecondP@ss#2026", "passport")
    raw = db_path.read_bytes()
    assert b"zf6114" not in raw
    assert b"SecondP@ss#2026" not in raw


def test_wrong_key_cannot_decrypt(tmp_path):
    db_path = tmp_path / "accounts.db"
    LocalAccountStore(str(db_path), KEY).add_account("wzj1004232242", "zf6114", "", "passport")
    wrong = LocalAccountStore(str(db_path), bytes(reversed(KEY)))
    with pytest.raises(Exception):
        wrong.list_accounts()


def test_add_account_with_device_code_and_phone(store):
    row = store.add_account(
        "by881119",
        "cd3835",
        "z878678",
        "passport",
        device_code="157bc3df28f459f0",
        phone="13357878267",
    )
    item = store.list_accounts()[0]
    assert item["device_code"] == "157bc3df28f459f0"
    assert item["phone"] == "13357878267"


def test_add_account_with_total_infull_num(store):
    store.add_account(
        "by881119", "cd3835", "", "passport", total_infull_num=27131, cannon=35000
    )
    item = store.list_accounts()[0]
    assert item["total_infull_num"] == 27131
    assert item["cannon"] == 35000


def test_update_account_cannon(store):
    row = store.add_account("by881119", "cd3835", "", "passport")
    store.update_account(row["id"], "cd3835", "", cannon=12000)
    assert store.list_accounts()[0]["cannon"] == 12000


def test_update_account_device_code_and_phone(store):
    row = store.add_account("by881119", "cd3835", "", "passport")
    store.update_account(row["id"], "cd3835", "", "79bde3ae35eb4043", "13800000000")
    item = store.list_accounts()[0]
    assert item["device_code"] == "79bde3ae35eb4043"
    assert item["phone"] == "13800000000"


def test_old_database_is_migrated(tmp_path):
    db_path = tmp_path / "old.db"
    conn = sqlite3.connect(str(db_path))
    conn.execute(
        """
        CREATE TABLE accounts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            account TEXT UNIQUE NOT NULL,
            enc_password TEXT NOT NULL,
            enc_secondary_password TEXT NOT NULL,
            login_type TEXT NOT NULL,
            cached_user_id INTEGER,
            nickname TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
        """
    )
    conn.commit()
    conn.close()

    LocalAccountStore(str(db_path), KEY).add_account("by881119", "cd3835", "", "passport")
    item = LocalAccountStore(str(db_path), KEY).list_accounts()[0]
    assert item["device_code"] == ""
    assert item["phone"] == ""
    assert item["total_infull_num"] == 0
    assert item["cannon"] == 0
    assert item["sort_order"] == 0


def test_add_account_default_sort_order_appends(store):
    first = store.add_account("a", "p1", "", "passport")
    second = store.add_account("b", "p2", "", "passport")
    items = store.list_accounts()
    assert [item["account"] for item in items] == ["a", "b"]
    assert [item["sort_order"] for item in items] == [0, 1]
    assert items[0]["id"] == first["id"]
    assert items[1]["id"] == second["id"]


def test_add_account_explicit_sort_order(store):
    store.add_account("a", "p1", "", "passport", sort_order=5)
    store.add_account("b", "p2", "", "passport", sort_order=2)
    items = store.list_accounts()
    assert [item["account"] for item in items] == ["b", "a"]
    assert [item["sort_order"] for item in items] == [2, 5]


def test_renumber_accounts_changes_order(store):
    a = store.add_account("a", "p1", "", "passport")
    b = store.add_account("b", "p2", "", "passport")
    c = store.add_account("c", "p3", "", "passport")
    store.renumber_accounts([c["id"], a["id"], b["id"]])
    items = store.list_accounts()
    assert [item["account"] for item in items] == ["c", "a", "b"]
    assert [item["sort_order"] for item in items] == [0, 1, 2]


def test_delete_account_renumbers(store):
    a = store.add_account("a", "p1", "", "passport")
    b = store.add_account("b", "p2", "", "passport")
    c = store.add_account("c", "p3", "", "passport")
    store.delete_account(b["id"])
    items = store.list_accounts()
    assert [item["account"] for item in items] == ["a", "c"]
    assert [item["sort_order"] for item in items] == [0, 1]
    assert a["id"] in [item["id"] for item in items]
    assert c["id"] in [item["id"] for item in items]
