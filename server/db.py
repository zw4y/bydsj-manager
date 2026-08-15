import sqlite3
from datetime import datetime, timedelta, timezone

BEIJING_TZ = timezone(timedelta(hours=8))


def beijing_now() -> str:
    return datetime.now(BEIJING_TZ).isoformat(timespec="seconds")


def connect(db_path: str) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def init_db(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS admin_users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            salt TEXT NOT NULL,
            created_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS card_keys (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            key_hash TEXT UNIQUE NOT NULL,
            status TEXT NOT NULL DEFAULT 'unused',
            expires_at TEXT,
            machine_id TEXT,
            bound_at TEXT,
            remark TEXT,
            created_at TEXT NOT NULL
        );
        """
    )
    columns = [row[1] for row in conn.execute("PRAGMA table_info(card_keys)").fetchall()]
    if "key_text" not in columns:
        conn.execute("ALTER TABLE card_keys ADD COLUMN key_text TEXT")
    conn.commit()


def ensure_admin(conn: sqlite3.Connection, admin_password: str) -> None:
    row = conn.execute("SELECT id FROM admin_users WHERE username = ?", ("admin",)).fetchone()
    if row:
        return
    from server.security import hash_password

    digest, salt = hash_password(admin_password)
    conn.execute(
        "INSERT INTO admin_users(username, password_hash, salt, created_at) VALUES (?, ?, ?, ?)",
        ("admin", digest, salt, beijing_now()),
    )
    conn.commit()
