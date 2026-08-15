import os
import secrets
import sqlite3
import csv
import calendar
import io
import json
import hashlib
import os
import re
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

from fastapi import Depends, FastAPI, File, Form, Header, HTTPException, Response, UploadFile
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from server.db import BEIJING_TZ, beijing_now, connect, ensure_admin, init_db
from server.security import create_jwt, decode_jwt, hash_password, verify_password


KEY_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"


def generate_card_key() -> str:
    groups = []
    for _ in range(4):
        groups.append("".join(secrets.choice(KEY_ALPHABET) for _ in range(4)))
    return "BYDSJ-" + "-".join(groups)


def add_months(value: datetime, months: int) -> datetime:
    month_index = value.month - 1 + months
    year = value.year + month_index // 12
    month = month_index % 12 + 1
    day = min(value.day, calendar.monthrange(year, month)[1])
    return value.replace(year=year, month=month, day=day)


CARD_DURATIONS = {
    "小时卡": ("hours", 1),
    "一天卡": ("hours", 24),
    "一周卡": ("days", 7),
    "一月卡": ("months", 1),
    "季度卡": ("months", 3),
    "半年卡": ("months", 6),
    "一年卡": ("months", 12),
    "两年卡": ("months", 24),
    "三年卡": ("months", 36),
}
LIFETIME_CARD = "终身卡"


def add_duration(value: datetime, card_type: str) -> datetime:
    unit, amount = CARD_DURATIONS[card_type]
    if unit == "months":
        return add_months(value, amount)
    if unit == "hours":
        return value + timedelta(hours=amount)
    return value + timedelta(days=amount)


def _is_expired(expires_at: str | None) -> bool:
    if not expires_at:
        return False
    try:
        exp = datetime.fromisoformat(expires_at)
        return exp < datetime.now(exp.tzinfo)
    except Exception:
        return True


class LoginBody(BaseModel):
    username: str
    password: str


class GenerateBody(BaseModel):
    count: int = Field(default=1, ge=1, le=200)
    expires_at: Optional[str] = None
    card_type: Optional[str] = None
    remark: Optional[str] = None


class RenewBody(BaseModel):
    card_type: str


class StatusBody(BaseModel):
    status: str


class ActivateBody(BaseModel):
    key: str
    machine_id: str = Field(min_length=8, max_length=128)


def create_app(
    db_path: str,
    jwt_secret: str,
    admin_password: str = "admin123",
    release_dir: str | None = None,
) -> FastAPI:
    app = FastAPI(title="卡密服务器")
    app.state.db_path = db_path
    app.state.jwt_secret = jwt_secret
    if release_dir is None:
        release_dir = os.environ.get("CARD_RELEASE_DIR", "/data/releases")
    release_dir = str(release_dir)
    Path(release_dir).mkdir(parents=True, exist_ok=True)
    app.state.release_dir = release_dir

    conn = connect(db_path)
    init_db(conn)
    ensure_admin(conn, admin_password)
    conn.close()

    def get_db():
        conn = connect(db_path)
        try:
            yield conn
        finally:
            conn.close()

    def require_admin(authorization: str = Header(default="")) -> str:
        if not authorization.startswith("Bearer "):
            raise HTTPException(status_code=401, detail="未登录")
        payload = decode_jwt(authorization[7:], jwt_secret)
        if not payload:
            raise HTTPException(status_code=401, detail="登录已失效")
        return payload["sub"]

    @app.post("/api/admin/login")
    def admin_login(body: LoginBody):
        conn = connect(db_path)
        try:
            row = conn.execute(
                "SELECT password_hash, salt FROM admin_users WHERE username = ?",
                (body.username,),
            ).fetchone()
        finally:
            conn.close()
        if not row or not verify_password(body.password, row["password_hash"], row["salt"]):
            raise HTTPException(status_code=401, detail="用户名或密码错误")
        return {"token": create_jwt(body.username, jwt_secret)}

    @app.post("/api/admin/keys/generate")
    def generate_keys(body: GenerateBody, _admin: str = Depends(require_admin)):
        keys = []
        conn = connect(db_path)
        try:
            for _ in range(body.count):
                key = generate_card_key()
                key_hash = hashlib.sha256(key.encode()).hexdigest()
                now = beijing_now()
                expires_at = body.expires_at
                if body.card_type:
                    if body.card_type == LIFETIME_CARD:
                        expires_at = None
                    elif body.card_type in CARD_DURATIONS:
                        expires_at = add_duration(
                            datetime.fromisoformat(now), body.card_type
                        ).isoformat(timespec="seconds")
                    else:
                        raise HTTPException(
                            status_code=400,
                            detail="卡型只能是 小时卡/一天卡/一周卡/一月卡/季度卡/半年卡/一年卡/两年卡/三年卡/终身卡",
                        )
                cur = conn.execute(
                    """
                    INSERT INTO card_keys(key_hash, key_text, status, expires_at, remark, created_at)
                    VALUES (?, ?, 'unused', ?, ?, ?)
                    """,
                    (key_hash, key, expires_at, body.remark, now),
                )
                keys.append({"id": cur.lastrowid, "key": key})
            conn.commit()
        finally:
            conn.close()
        return {"keys": keys}

    @app.get("/api/admin/keys")
    def list_keys(status: Optional[str] = None, _admin: str = Depends(require_admin)):
        conn = connect(db_path)
        try:
            if status:
                rows = conn.execute(
                    "SELECT id, key_text AS key, status, expires_at, machine_id, bound_at, remark, created_at "
                    "FROM card_keys WHERE status = ? ORDER BY id DESC",
                    (status,),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT id, key_text AS key, status, expires_at, machine_id, bound_at, remark, created_at "
                    "FROM card_keys ORDER BY id DESC"
                ).fetchall()
        finally:
            conn.close()
        return {"items": [dict(row) for row in rows]}

    @app.get("/api/admin/keys/export")
    def export_keys(_admin: str = Depends(require_admin)):
        conn = connect(db_path)
        try:
            rows = conn.execute(
                "SELECT id, key_text AS key, status, expires_at, machine_id, bound_at, remark, created_at "
                "FROM card_keys ORDER BY id DESC"
            ).fetchall()
        finally:
            conn.close()
        buf = io.StringIO()
        writer = csv.writer(buf)
        writer.writerow(["id", "key", "status", "expires_at", "machine_id", "bound_at", "remark", "created_at"])
        for row in rows:
            writer.writerow([row["id"], row["key"], row["status"], row["expires_at"], row["machine_id"], row["bound_at"], row["remark"], row["created_at"]])
        return Response(
            content=buf.getvalue(),
            media_type="text/csv; charset=utf-8",
            headers={"Content-Disposition": "attachment; filename=card_keys.csv"},
        )

    @app.patch("/api/admin/keys/{key_id}/status")
    def update_status(key_id: int, body: StatusBody, _admin: str = Depends(require_admin)):
        if body.status not in {"active", "disabled"}:
            raise HTTPException(status_code=400, detail="状态只能是 active/disabled")
        conn = connect(db_path)
        try:
            cur = conn.execute("UPDATE card_keys SET status = ? WHERE id = ?", (body.status, key_id))
            conn.commit()
        finally:
            conn.close()
        if cur.rowcount == 0:
            raise HTTPException(status_code=404, detail="卡密不存在")
        return {"ok": True}

    @app.post("/api/admin/keys/{key_id}/unbind")
    def unbind(key_id: int, _admin: str = Depends(require_admin)):
        conn = connect(db_path)
        try:
            cur = conn.execute(
                "UPDATE card_keys SET machine_id = NULL, bound_at = NULL, status = 'unused' WHERE id = ?",
                (key_id,),
            )
            conn.commit()
        finally:
            conn.close()
        if cur.rowcount == 0:
            raise HTTPException(status_code=404, detail="卡密不存在")
        return {"ok": True}

    @app.post("/api/admin/keys/{key_id}/renew")
    def renew_key(
        key_id: int, body: RenewBody, _admin: str = Depends(require_admin)
    ):
        if body.card_type != LIFETIME_CARD and body.card_type not in CARD_DURATIONS:
            raise HTTPException(
                status_code=400,
                detail="卡型只能是 小时卡/一天卡/一周卡/一月卡/季度卡/半年卡/一年卡/两年卡/三年卡/终身卡",
            )
        conn = connect(db_path)
        try:
            row = conn.execute(
                "SELECT expires_at FROM card_keys WHERE id = ?", (key_id,)
            ).fetchone()
            if not row:
                raise HTTPException(status_code=404, detail="卡密不存在")
            if row["expires_at"] is None:
                raise HTTPException(status_code=400, detail="该卡密已是终身卡，无需续费")
            if body.card_type == LIFETIME_CARD:
                conn.execute(
                    "UPDATE card_keys SET expires_at = NULL WHERE id = ?", (key_id,)
                )
                conn.commit()
                return {"ok": True, "expires_at": None}
            if _is_expired(row["expires_at"]):
                base = datetime.fromisoformat(beijing_now())
            else:
                base = datetime.fromisoformat(row["expires_at"])
            new_expires = add_duration(base, body.card_type).isoformat(timespec="seconds")
            conn.execute(
                "UPDATE card_keys SET expires_at = ? WHERE id = ?",
                (new_expires, key_id),
            )
            conn.commit()
        finally:
            conn.close()
        return {"ok": True, "expires_at": new_expires}

    @app.delete("/api/admin/keys/{key_id}")
    def delete_key(key_id: int, _admin: str = Depends(require_admin)):
        conn = connect(db_path)
        try:
            cur = conn.execute("DELETE FROM card_keys WHERE id = ?", (key_id,))
            conn.commit()
        finally:
            conn.close()
        if cur.rowcount == 0:
            raise HTTPException(status_code=404, detail="卡密不存在")
        return {"ok": True}

    @app.post("/api/admin/release")
    def publish_release(
        version: str = Form(...),
        note: str = Form(""),
        file: UploadFile = File(...),
        _admin: str = Depends(require_admin),
    ):
        if not re.fullmatch(r"\d+\.\d+\.\d+", version):
            raise HTTPException(status_code=400, detail="版本号格式应为 x.y.z")
        if not file.filename or not file.filename.lower().endswith(".exe"):
            raise HTTPException(status_code=400, detail="只能上传 .exe 文件")
        dest = Path(release_dir) / f"app_{version}.exe"
        sha = hashlib.sha256()
        size = 0
        with dest.open("wb") as out:
            while chunk := file.file.read(1024 * 1024):
                size += len(chunk)
                if size > 200 * 1024 * 1024:
                    raise HTTPException(status_code=413, detail="文件过大，最大 200MB")
                sha.update(chunk)
                out.write(chunk)
        manifest = {
            "version": version,
            "url": f"/releases/app_{version}.exe",
            "sha256": sha.hexdigest(),
            "note": note,
        }
        version_path = Path(release_dir) / "version.json"
        tmp_path = version_path.with_suffix(".tmp")
        tmp_path.write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        tmp_path.replace(version_path)
        return {"ok": True, **manifest}

    @app.get("/api/client/version")
    def client_version():
        version_path = Path(release_dir) / "version.json"
        if not version_path.exists():
            raise HTTPException(status_code=404, detail="暂无更新")
        return json.loads(version_path.read_text(encoding="utf-8"))

    app.mount("/releases", StaticFiles(directory=release_dir), name="releases")

    def _check_key(key: str, machine_id: str, bind_if_unused: bool):
        key_hash = hashlib.sha256(key.encode()).hexdigest()
        conn = connect(db_path)
        try:
            row = conn.execute("SELECT * FROM card_keys WHERE key_hash = ?", (key_hash,)).fetchone()
            if not row:
                raise HTTPException(status_code=404, detail="卡密不存在")
            if row["status"] == "disabled":
                raise HTTPException(status_code=403, detail="卡密已被停用")
            if _is_expired(row["expires_at"]):
                raise HTTPException(status_code=403, detail="卡密已过期")
            if row["machine_id"] is None:
                if bind_if_unused:
                    conn.execute(
                        "UPDATE card_keys SET machine_id = ?, bound_at = ?, status = 'active' WHERE id = ?",
                        (machine_id, beijing_now(), row["id"]),
                    )
                    conn.commit()
                    return row["expires_at"], True
                raise HTTPException(status_code=409, detail="卡密尚未激活")
            if row["machine_id"] != machine_id:
                raise HTTPException(status_code=409, detail="卡密已绑定其他机器，请联系管理员解绑")
            return row["expires_at"], False
        finally:
            conn.close()

    @app.post("/api/client/activate")
    def activate(body: ActivateBody):
        expires_at, bound = _check_key(body.key, body.machine_id, bind_if_unused=True)
        return {"ok": True, "bound": bound, "expires_at": expires_at}

    @app.post("/api/client/validate")
    def validate(body: ActivateBody):
        expires_at, _ = _check_key(body.key, body.machine_id, bind_if_unused=False)
        return {"ok": True, "expires_at": expires_at}

    return app
