"""卡密服务器客户端与本地密钥派生。"""

from __future__ import annotations

import hashlib
import os
import platform
import socket
import uuid
from pathlib import Path

import httpx


class CardAuthError(RuntimeError):
    pass


def machine_id() -> str:
    raw = "|".join(
        [
            str(uuid.getnode()),
            platform.node(),
            platform.machine(),
            platform.system(),
            socket.gethostname(),
        ]
    )
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def derive_key(card_key: str, machine: str, salt: bytes) -> bytes:
    return hashlib.scrypt(
        password=card_key.encode("utf-8"),
        salt=salt + machine.encode("utf-8"),
        n=2**14,
        r=8,
        p=1,
        dklen=32,
    )


def key_hash(card_key: str) -> str:
    return hashlib.sha256(card_key.encode("utf-8")).hexdigest()


def mask_card_key(card_key: str) -> str:
    """脱敏卡密：保留前缀与末尾 4 位，中间用 X 代替，用于日志展示。"""
    key = (card_key or "").strip()
    if not key:
        return ""
    if len(key) <= 10:
        return "*" * len(key)
    return key[:6] + "XXXX-XXXX-XXXX-" + key[-4:]


def profile_root() -> Path:
    base = os.environ.get("APPDATA") or str(Path.home() / ".config")
    return Path(base) / "BydsjManager"


def profile_dir(card_key: str) -> Path:
    return profile_root() / key_hash(card_key)


class CardAuthClient:
    def __init__(self, server_url: str, http_client: httpx.Client | None = None, timeout: float = 15.0):
        self._server_url = server_url.rstrip("/")
        self._http = http_client or httpx.Client(timeout=timeout, trust_env=False)

    def _post(self, path: str, body: dict) -> dict:
        resp = self._http.post(self._server_url + path, json=body)
        try:
            data = resp.json()
        except Exception:
            data = {"detail": resp.text[:200]}
        if resp.status_code >= 400:
            raise CardAuthError(data.get("detail", f"服务器错误 {resp.status_code}"))
        return data

    def activate(self, key: str, machine: str) -> dict:
        return self._post("/api/client/activate", {"key": key, "machine_id": machine})

    def validate(self, key: str, machine: str) -> dict:
        return self._post("/api/client/validate", {"key": key, "machine_id": machine})
