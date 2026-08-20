"""Small local SQLite profile and model-library store.

Profiles deliberately live on the host PC, so they persist across browser
devices while the public tunnel is running without relying on a third party.
"""
from __future__ import annotations

import hashlib
import hmac
import secrets
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path


class ProfileStore:
    def __init__(self, database: Path) -> None:
        self.database = database
        self.database.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS profiles (
                    id TEXT PRIMARY KEY, display_name TEXT NOT NULL UNIQUE COLLATE NOCASE,
                    password_salt BLOB NOT NULL, password_hash BLOB NOT NULL,
                    created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS sessions (
                    token_hash TEXT PRIMARY KEY, profile_id TEXT NOT NULL,
                    expires_at TEXT NOT NULL, FOREIGN KEY(profile_id) REFERENCES profiles(id)
                );
                CREATE TABLE IF NOT EXISTS saved_models (
                    id TEXT PRIMARY KEY, profile_id TEXT NOT NULL, generation_id TEXT NOT NULL,
                    title TEXT NOT NULL, created_at TEXT NOT NULL,
                    UNIQUE(profile_id, generation_id), FOREIGN KEY(profile_id) REFERENCES profiles(id)
                );
            """)

    def _connect(self) -> sqlite3.Connection:
        db = sqlite3.connect(self.database)
        db.row_factory = sqlite3.Row
        return db

    @staticmethod
    def _password_hash(password: str, salt: bytes) -> bytes:
        return hashlib.scrypt(password.encode("utf-8"), salt=salt, n=2**14, r=8, p=1)

    @staticmethod
    def _now() -> str:
        return datetime.now(timezone.utc).isoformat()

    def create_profile(self, display_name: str, password: str) -> dict[str, str]:
        name = display_name.strip()
        if not 2 <= len(name) <= 40:
            raise ValueError("Profile name must be 2–40 characters.")
        if len(password) < 8:
            raise ValueError("Password must be at least 8 characters.")
        profile_id, salt = secrets.token_hex(16), secrets.token_bytes(16)
        try:
            with self._connect() as db:
                db.execute("INSERT INTO profiles VALUES (?, ?, ?, ?, ?)",
                    (profile_id, name, salt, self._password_hash(password, salt), self._now()))
        except sqlite3.IntegrityError as exc:
            raise ValueError("That profile name is already in use.") from exc
        return {"id": profile_id, "display_name": name}

    def authenticate(self, display_name: str, password: str) -> dict[str, str] | None:
        with self._connect() as db:
            row = db.execute("SELECT * FROM profiles WHERE display_name = ?", (display_name.strip(),)).fetchone()
        if row is None or not hmac.compare_digest(row["password_hash"], self._password_hash(password, row["password_salt"])):
            return None
        return {"id": row["id"], "display_name": row["display_name"]}

    def create_session(self, profile_id: str) -> str:
        token = secrets.token_urlsafe(32)
        expires = (datetime.now(timezone.utc) + timedelta(days=30)).isoformat()
        with self._connect() as db:
            db.execute("INSERT INTO sessions VALUES (?, ?, ?)", (hashlib.sha256(token.encode()).hexdigest(), profile_id, expires))
        return token

    def profile_for_token(self, token: str | None) -> dict[str, str] | None:
        if not token:
            return None
        with self._connect() as db:
            row = db.execute("""SELECT profiles.id, profiles.display_name FROM sessions JOIN profiles ON profiles.id = sessions.profile_id
                WHERE sessions.token_hash = ? AND sessions.expires_at > ?""", (hashlib.sha256(token.encode()).hexdigest(), self._now())).fetchone()
        return dict(row) if row else None

    def delete_session(self, token: str | None) -> None:
        if token:
            with self._connect() as db:
                db.execute("DELETE FROM sessions WHERE token_hash = ?", (hashlib.sha256(token.encode()).hexdigest(),))

    def save_model(self, profile_id: str, generation_id: str, title: str) -> None:
        with self._connect() as db:
            db.execute("INSERT OR IGNORE INTO saved_models VALUES (?, ?, ?, ?, ?)",
                (secrets.token_hex(16), profile_id, generation_id, title[:80] or "Untitled model", self._now()))

    def list_models(self, profile_id: str) -> list[dict[str, str]]:
        with self._connect() as db:
            rows = db.execute("SELECT id, generation_id, title, created_at FROM saved_models WHERE profile_id = ? ORDER BY created_at DESC", (profile_id,)).fetchall()
        return [dict(row) for row in rows]

    def get_model(self, profile_id: str, model_id: str) -> dict[str, str] | None:
        with self._connect() as db:
            row = db.execute("SELECT id, generation_id, title, created_at FROM saved_models WHERE profile_id = ? AND id = ?", (profile_id, model_id)).fetchone()
        return dict(row) if row else None
