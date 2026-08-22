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
                    title TEXT NOT NULL, created_at TEXT NOT NULL, folder_id TEXT,
                    UNIQUE(profile_id, generation_id), FOREIGN KEY(profile_id) REFERENCES profiles(id)
                );
                CREATE TABLE IF NOT EXISTS library_folders (
                    id TEXT PRIMARY KEY, profile_id TEXT NOT NULL, name TEXT NOT NULL,
                    created_at TEXT NOT NULL, UNIQUE(profile_id, name COLLATE NOCASE),
                    FOREIGN KEY(profile_id) REFERENCES profiles(id)
                );
                CREATE TABLE IF NOT EXISTS model_shares (
                    token TEXT PRIMARY KEY, profile_id TEXT NOT NULL, model_id TEXT NOT NULL,
                    allow_download INTEGER NOT NULL, expires_at TEXT NOT NULL, created_at TEXT NOT NULL,
                    FOREIGN KEY(profile_id) REFERENCES profiles(id)
                );
            """)
            columns = {row[1] for row in db.execute("PRAGMA table_info(saved_models)")}
            if "folder_id" not in columns:
                db.execute("ALTER TABLE saved_models ADD COLUMN folder_id TEXT")
            if "tags" not in columns:
                db.execute("ALTER TABLE saved_models ADD COLUMN tags TEXT NOT NULL DEFAULT ''")

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

    def save_model(self, profile_id: str, generation_id: str, title: str, folder_id: str | None = None) -> None:
        with self._connect() as db:
            db.execute(
                "INSERT OR IGNORE INTO saved_models (id, profile_id, generation_id, title, created_at, folder_id) VALUES (?, ?, ?, ?, ?, ?)",
                (secrets.token_hex(16), profile_id, generation_id, title[:80] or "Untitled model", self._now(), folder_id),
            )

    def list_models(self, profile_id: str) -> list[dict[str, str]]:
        with self._connect() as db:
            rows = db.execute("SELECT id, generation_id, title, created_at, folder_id, tags FROM saved_models WHERE profile_id = ? ORDER BY created_at DESC", (profile_id,)).fetchall()
        return [dict(row) for row in rows]

    def get_model(self, profile_id: str, model_id: str) -> dict[str, str] | None:
        with self._connect() as db:
            row = db.execute("SELECT id, generation_id, title, created_at, folder_id, tags FROM saved_models WHERE profile_id = ? AND id = ?", (profile_id, model_id)).fetchone()
        return dict(row) if row else None

    def rename_model(self, profile_id: str, model_id: str, title: str) -> dict[str, str] | None:
        clean_title = title.strip()
        if not 1 <= len(clean_title) <= 80:
            raise ValueError("Model name must be 1–80 characters.")
        with self._connect() as db:
            result = db.execute(
                "UPDATE saved_models SET title = ? WHERE profile_id = ? AND id = ?",
                (clean_title, profile_id, model_id),
            )
        if result.rowcount != 1:
            return None
        return self.get_model(profile_id, model_id)

    def delete_model(self, profile_id: str, model_id: str) -> bool:
        """Remove a library entry without deleting its generated GLB file."""
        with self._connect() as db:
            result = db.execute(
                "DELETE FROM saved_models WHERE profile_id = ? AND id = ?",
                (profile_id, model_id),
            )
        return result.rowcount == 1

    def list_folders(self, profile_id: str) -> list[dict[str, str]]:
        with self._connect() as db:
            rows = db.execute(
                "SELECT id, name, created_at FROM library_folders WHERE profile_id = ? ORDER BY name COLLATE NOCASE",
                (profile_id,),
            ).fetchall()
        return [dict(row) for row in rows]

    def create_folder(self, profile_id: str, name: str) -> dict[str, str]:
        clean_name = name.strip()
        if not 1 <= len(clean_name) <= 50:
            raise ValueError("Folder name must be 1–50 characters.")
        folder = {"id": secrets.token_hex(16), "name": clean_name, "created_at": self._now()}
        try:
            with self._connect() as db:
                db.execute(
                    "INSERT INTO library_folders (id, profile_id, name, created_at) VALUES (?, ?, ?, ?)",
                    (folder["id"], profile_id, folder["name"], folder["created_at"]),
                )
        except sqlite3.IntegrityError as exc:
            raise ValueError("That folder name is already in use.") from exc
        return folder

    def rename_folder(self, profile_id: str, folder_id: str, name: str) -> dict[str, str] | None:
        clean_name = name.strip()
        if not 1 <= len(clean_name) <= 50:
            raise ValueError("Folder name must be 1–50 characters.")
        try:
            with self._connect() as db:
                result = db.execute(
                    "UPDATE library_folders SET name = ? WHERE id = ? AND profile_id = ?",
                    (clean_name, folder_id, profile_id),
                )
                if result.rowcount != 1:
                    return None
                row = db.execute("SELECT id, name, created_at FROM library_folders WHERE id = ?", (folder_id,)).fetchone()
        except sqlite3.IntegrityError as exc:
            raise ValueError("That folder name is already in use.") from exc
        return dict(row) if row else None

    def delete_folder(self, profile_id: str, folder_id: str) -> bool:
        """Remove a folder while keeping its models in the unfiled section."""
        with self._connect() as db:
            db.execute("UPDATE saved_models SET folder_id = NULL WHERE profile_id = ? AND folder_id = ?", (profile_id, folder_id))
            result = db.execute("DELETE FROM library_folders WHERE id = ? AND profile_id = ?", (folder_id, profile_id))
        return result.rowcount == 1

    def move_model(self, profile_id: str, model_id: str, folder_id: str | None) -> dict[str, str] | None:
        with self._connect() as db:
            if folder_id:
                folder = db.execute("SELECT 1 FROM library_folders WHERE id = ? AND profile_id = ?", (folder_id, profile_id)).fetchone()
                if folder is None:
                    return None
            result = db.execute(
                "UPDATE saved_models SET folder_id = ? WHERE id = ? AND profile_id = ?",
                (folder_id, model_id, profile_id),
            )
        return self.get_model(profile_id, model_id) if result.rowcount == 1 else None

    def tag_model(self, profile_id: str, model_id: str, tags: str) -> dict[str, str] | None:
        clean = ", ".join(dict.fromkeys(part.strip() for part in tags.split(",") if part.strip()))[:200]
        with self._connect() as db:
            result = db.execute("UPDATE saved_models SET tags = ? WHERE id = ? AND profile_id = ?", (clean, model_id, profile_id))
        return self.get_model(profile_id, model_id) if result.rowcount == 1 else None

    def create_share(self, profile_id: str, model_id: str, allow_download: bool, days: int = 7) -> dict[str, str | bool]:
        model = self.get_model(profile_id, model_id)
        if model is None:
            raise ValueError("Saved model not found.")
        token = secrets.token_urlsafe(24)
        expires = (datetime.now(timezone.utc) + timedelta(days=max(1, min(days, 30)))).isoformat()
        with self._connect() as db:
            db.execute(
                "INSERT INTO model_shares VALUES (?, ?, ?, ?, ?, ?)",
                (token, profile_id, model_id, int(allow_download), expires, self._now()),
            )
        return {"token": token, "allow_download": allow_download, "expires_at": expires}

    def get_share(self, token: str) -> dict[str, str | int] | None:
        with self._connect() as db:
            row = db.execute(
                """SELECT model_shares.token, model_shares.allow_download, model_shares.expires_at,
                   saved_models.generation_id, saved_models.title
                   FROM model_shares JOIN saved_models ON saved_models.id = model_shares.model_id
                   WHERE model_shares.token = ? AND model_shares.expires_at > ?""",
                (token, self._now()),
            ).fetchone()
        return dict(row) if row else None
