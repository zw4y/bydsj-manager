import hashlib
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from server.app import create_app  # noqa: E402


@pytest.fixture()
def client(tmp_path):
    db_path = tmp_path / "cards.db"
    release_dir = tmp_path / "releases"
    app = create_app(
        db_path=str(db_path),
        jwt_secret="test-secret",
        release_dir=str(release_dir),
    )
    with TestClient(app) as test_client:
        yield test_client


def admin_headers(client):
    resp = client.post("/api/admin/login", json={"username": "admin", "password": "admin123"})
    token = resp.json()["token"]
    return {"Authorization": f"Bearer {token}"}


def test_version_returns_404_before_publish(client):
    resp = client.get("/api/client/version")
    assert resp.status_code == 404


def test_publish_requires_admin_auth(client):
    resp = client.post("/api/admin/release", files={"file": ("app.exe", b"x")})
    assert resp.status_code == 401


def test_publish_release_and_download(client):
    payload = b"MZ fake exe content"
    resp = client.post(
        "/api/admin/release",
        data={"version": "1.0.1", "note": "test release"},
        files={"file": ("app.exe", payload)},
        headers=admin_headers(client),
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["version"] == "1.0.1"
    assert body["sha256"] == hashlib.sha256(payload).hexdigest()

    version = client.get("/api/client/version").json()
    assert version["version"] == "1.0.1"
    assert version["note"] == "test release"

    downloaded = client.get(version["url"])
    assert downloaded.status_code == 200
    assert downloaded.content == payload


def test_publish_rejects_bad_version_and_non_exe(client):
    headers = admin_headers(client)
    resp = client.post(
        "/api/admin/release",
        data={"version": "abc"},
        files={"file": ("app.exe", b"x")},
        headers=headers,
    )
    assert resp.status_code == 400
    resp = client.post(
        "/api/admin/release",
        data={"version": "1.0.2"},
        files={"file": ("app.zip", b"x")},
        headers=headers,
    )
    assert resp.status_code == 400
