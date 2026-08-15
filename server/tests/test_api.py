import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from server.app import create_app  # noqa: E402


@pytest.fixture()
def client(tmp_path):
    db_path = tmp_path / "cards.db"
    app = create_app(
        db_path=str(db_path),
        jwt_secret="test-secret",
        release_dir=str(tmp_path / "releases"),
    )
    with TestClient(app) as test_client:
        yield test_client


def admin_headers(client):
    resp = client.post("/api/admin/login", json={"username": "admin", "password": "admin123"})
    assert resp.status_code == 200
    token = resp.json()["token"]
    return {"Authorization": f"Bearer {token}"}


def generate_keys(client, count=1, **kwargs):
    resp = client.post("/api/admin/keys/generate", json={"count": count, **kwargs}, headers=admin_headers(client))
    assert resp.status_code == 200
    return resp.json()["keys"]


def test_generate_keys_requires_admin_auth(client):
    resp = client.post("/api/admin/keys/generate", json={"count": 1})
    assert resp.status_code == 401


def test_admin_login_and_generate_formatted_keys(client):
    keys = generate_keys(client, count=2)
    assert len(keys) == 2
    assert all(k["key"].startswith("BYDSJ-") and len(k["key"]) == 25 for k in keys)


def test_admin_list_returns_plaintext_keys(client):
    keys = generate_keys(client, count=1)
    resp = client.get("/api/admin/keys", headers=admin_headers(client))
    assert resp.status_code == 200
    items = resp.json()["items"]
    assert items[0]["key"] == keys[0]["key"]


def test_generate_with_card_type_sets_future_expiry(client):
    generate_keys(client, count=1, card_type="一年卡")
    items = client.get("/api/admin/keys", headers=admin_headers(client)).json()["items"]
    assert items[0]["expires_at"] is not None
    exp = datetime.fromisoformat(items[0]["expires_at"])
    assert exp.tzinfo is not None
    assert exp.utcoffset() == timedelta(hours=8)
    assert exp > datetime.now(timezone(timedelta(hours=8)))


def test_admin_export_returns_csv(client):
    generate_keys(client, count=1)
    resp = client.get("/api/admin/keys/export", headers=admin_headers(client))
    assert resp.status_code == 200
    assert "text/csv" in resp.headers["content-type"]
    assert "id,key,status,expires_at,machine_id,bound_at,remark,created_at" in resp.text


def test_activate_binds_first_machine_and_accepts_same_machine(client):
    key = generate_keys(client)[0]["key"]
    first = client.post("/api/client/activate", json={"key": key, "machine_id": "machine-001"})
    assert first.status_code == 200
    assert first.json()["ok"] is True
    same = client.post("/api/client/activate", json={"key": key, "machine_id": "machine-001"})
    assert same.status_code == 200


def test_activate_rejects_other_machine(client):
    key = generate_keys(client)[0]["key"]
    client.post("/api/client/activate", json={"key": key, "machine_id": "machine-001"})
    resp = client.post("/api/client/activate", json={"key": key, "machine_id": "machine-002"})
    assert resp.status_code == 409


def test_activate_rejects_expired_key(client):
    key = generate_keys(client, expires_at="2000-01-01T00:00:00")[0]["key"]
    resp = client.post("/api/client/activate", json={"key": key, "machine_id": "machine-001"})
    assert resp.status_code == 403


def test_activate_rejects_disabled_key(client):
    key_info = generate_keys(client)[0]
    key_id = key_info["id"]
    resp = client.patch(
        f"/api/admin/keys/{key_id}/status",
        json={"status": "disabled"},
        headers=admin_headers(client),
    )
    assert resp.status_code == 200
    resp = client.post("/api/client/activate", json={"key": key_info["key"], "machine_id": "machine-001"})
    assert resp.status_code == 403


def test_admin_unbind_allows_rebind_to_new_machine(client):
    key = generate_keys(client)[0]["key"]
    client.post("/api/client/activate", json={"key": key, "machine_id": "machine-001"})
    keys = client.get("/api/admin/keys", headers=admin_headers(client)).json()["items"]
    key_id = keys[0]["id"]
    resp = client.post(f"/api/admin/keys/{key_id}/unbind", headers=admin_headers(client))
    assert resp.status_code == 200
    resp = client.post("/api/client/activate", json={"key": key, "machine_id": "machine-002"})
    assert resp.status_code == 200


def test_validate_requires_active_binding_on_same_machine(client):
    key = generate_keys(client)[0]["key"]
    client.post("/api/client/activate", json={"key": key, "machine_id": "machine-001"})
    ok = client.post("/api/client/validate", json={"key": key, "machine_id": "machine-001"})
    assert ok.status_code == 200
    bad = client.post("/api/client/validate", json={"key": key, "machine_id": "machine-002"})
    assert bad.status_code == 409


def test_generate_supports_all_card_types(client):
    headers = admin_headers(client)
    now = datetime.now(timezone(timedelta(hours=8)))
    expectations = {
        "小时卡": (now + timedelta(hours=1), 10),
        "一天卡": (now + timedelta(hours=24), 10),
        "一周卡": (now + timedelta(days=7), 60),
        "一月卡": (now + timedelta(days=20), 40),
        "季度卡": (now + timedelta(days=80), 100),
        "半年卡": (now + timedelta(days=170), 200),
        "一年卡": (now + timedelta(days=350), 400),
        "两年卡": (now + timedelta(days=700), 760),
        "三年卡": (now + timedelta(days=1050), 1120),
    }
    for card_type, (low, high) in expectations.items():
        key = generate_keys(client, count=1, card_type=card_type)[0]["key"]
        items = client.get("/api/admin/keys", headers=headers).json()["items"]
        item = next(i for i in items if i["key"] == key)
        exp = datetime.fromisoformat(item["expires_at"])
        assert low - timedelta(minutes=5) <= exp <= now + timedelta(days=high), card_type

    lifetime = generate_keys(client, count=1, card_type="终身卡")[0]["key"]
    items = client.get("/api/admin/keys", headers=headers).json()["items"]
    lifetime_item = next(i for i in items if i["key"] == lifetime)
    assert lifetime_item["expires_at"] is None


def test_renew_extends_active_card(client):
    info = generate_keys(client, count=1, card_type="一年卡")[0]
    before = datetime.fromisoformat(
        client.get("/api/admin/keys", headers=admin_headers(client)).json()["items"][0]["expires_at"]
    )
    resp = client.post(
        f"/api/admin/keys/{info['id']}/renew",
        json={"card_type": "一年卡"},
        headers=admin_headers(client),
    )
    assert resp.status_code == 200
    after = datetime.fromisoformat(resp.json()["expires_at"])
    assert timedelta(days=300) < (after - before) < timedelta(days=400)


def test_renew_expired_card_from_now(client):
    info = generate_keys(client, expires_at="2000-01-01T00:00:00+08:00")[0]
    resp = client.post(
        f"/api/admin/keys/{info['id']}/renew",
        json={"card_type": "小时卡"},
        headers=admin_headers(client),
    )
    assert resp.status_code == 200
    after = datetime.fromisoformat(resp.json()["expires_at"])
    now = datetime.now(timezone(timedelta(hours=8)))
    assert after > now + timedelta(minutes=30)


def test_renew_lifetime_card_rejected(client):
    info = generate_keys(client, card_type="终身卡")[0]
    resp = client.post(
        f"/api/admin/keys/{info['id']}/renew",
        json={"card_type": "一年卡"},
        headers=admin_headers(client),
    )
    assert resp.status_code == 400


def test_renew_missing_card_404(client):
    resp = client.post(
        "/api/admin/keys/999999/renew",
        json={"card_type": "一年卡"},
        headers=admin_headers(client),
    )
    assert resp.status_code == 404


def test_delete_card_removes_and_invalidates(client):
    info = generate_keys(client)[0]
    resp = client.delete(
        f"/api/admin/keys/{info['id']}", headers=admin_headers(client)
    )
    assert resp.status_code == 200
    activate = client.post(
        "/api/client/activate",
        json={"key": info["key"], "machine_id": "machine-001"},
    )
    assert activate.status_code == 404
    items = client.get("/api/admin/keys", headers=admin_headers(client)).json()["items"]
    assert all(i["id"] != info["id"] for i in items)


def test_times_are_beijing_timezone(client):
    generate_keys(client, count=1, card_type="一年卡")
    item = client.get("/api/admin/keys", headers=admin_headers(client)).json()["items"][0]
    for key in ("created_at", "expires_at"):
        dt = datetime.fromisoformat(item[key])
        assert dt.utcoffset() == timedelta(hours=8)
