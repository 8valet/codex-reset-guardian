from __future__ import annotations

import json
import os
import sqlite3
import time
import uuid
from pathlib import Path
from typing import Any


class AccountChanged(RuntimeError):
    pass


class Store:
    def __init__(self, path: Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        if os.name != "nt":
            try:
                os.chmod(self.path.parent, 0o700)
            except OSError:
                pass

        self.db = sqlite3.connect(self.path)
        self.db.row_factory = sqlite3.Row

        if os.name != "nt":
            try:
                os.chmod(self.path, 0o600)
            except OSError:
                pass

        self.db.executescript(
            """
            PRAGMA journal_mode=WAL;
            CREATE TABLE IF NOT EXISTS meta(
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS credits(
                id TEXT PRIMARY KEY,
                title TEXT,
                status TEXT,
                expires_at INTEGER,
                granted_at INTEGER,
                last_seen_at INTEGER NOT NULL,
                preflight_done INTEGER NOT NULL DEFAULT 0
            );
            CREATE TABLE IF NOT EXISTS attempts(
                credit_id TEXT NOT NULL,
                slot_seconds INTEGER NOT NULL,
                idempotency_key TEXT NOT NULL,
                created_at INTEGER NOT NULL,
                last_try_at INTEGER,
                network_retries INTEGER NOT NULL DEFAULT 0,
                outcome TEXT,
                error TEXT,
                PRIMARY KEY(credit_id, slot_seconds)
            );
            CREATE TABLE IF NOT EXISTS mutes(
                credit_id TEXT PRIMARY KEY,
                muted INTEGER NOT NULL
            );
            CREATE TABLE IF NOT EXISTS reminder_state(
                credit_id TEXT PRIMARY KEY,
                remaining_seconds INTEGER,
                eligibility INTEGER,
                updated_at INTEGER NOT NULL
            );
            CREATE TABLE IF NOT EXISTS events(
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ts INTEGER NOT NULL,
                level TEXT NOT NULL,
                event TEXT NOT NULL,
                details TEXT
            );
            CREATE TABLE IF NOT EXISTS sent_events(
                dedupe_key TEXT PRIMARY KEY,
                sent_at INTEGER NOT NULL
            );
            CREATE TABLE IF NOT EXISTS notification_outbox(
                dedupe_key TEXT PRIMARY KEY,
                event_json TEXT NOT NULL,
                created_at INTEGER NOT NULL,
                last_attempt_at INTEGER,
                last_error TEXT
            );
            """
        )
        if self.get_meta("armed") is None:
            self.set_meta("armed", "0")

    def __enter__(self) -> "Store":
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    def close(self) -> None:
        db = getattr(self, "db", None)
        if db is not None:
            db.close()
            self.db = None

    def __del__(self) -> None:
        try:
            self.close()
        except Exception:
            pass

    def get_meta(self, key: str) -> str | None:
        row = self.db.execute(
            "SELECT value FROM meta WHERE key=?",
            (key,),
        ).fetchone()
        return row["value"] if row else None

    def set_meta(self, key: str, value: str) -> None:
        self.db.execute(
            """
            INSERT INTO meta(key, value)
            VALUES(?, ?)
            ON CONFLICT(key) DO UPDATE SET value=excluded.value
            """,
            (key, value),
        )
        self.db.commit()

    def is_armed(self) -> bool:
        return self.get_meta("armed") == "1"

    def set_armed(self, value: bool) -> None:
        self.set_meta("armed", "1" if value else "0")

    def pin_account(self, account_id: str) -> None:
        if not account_id:
            raise ValueError("missing account id")

        pinned = self.get_meta("pinned_account_id")
        if pinned is None:
            self.set_meta("pinned_account_id", account_id)
            return
        if pinned != account_id:
            self.set_armed(False)
            raise AccountChanged(
                "Codex account changed; Guardian automatically disarmed"
            )

    def repin(self, account_id: str) -> None:
        self.set_meta("pinned_account_id", account_id)
        self.set_armed(False)

    def sync_credits(self, credits: list[dict[str, Any]]) -> None:
        now = int(time.time())
        for credit in credits:
            self.db.execute(
                """
                INSERT INTO credits(
                    id, title, status, expires_at, granted_at, last_seen_at
                )
                VALUES(?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    title=excluded.title,
                    status=excluded.status,
                    expires_at=excluded.expires_at,
                    granted_at=excluded.granted_at,
                    last_seen_at=excluded.last_seen_at
                """,
                (
                    str(credit.get("id")),
                    credit.get("title"),
                    credit.get("status"),
                    credit.get("expiresAt"),
                    credit.get("grantedAt"),
                    now,
                ),
            )
        self.db.commit()

    def current_credits(self) -> list[dict[str, Any]]:
        rows = self.db.execute(
            "SELECT * FROM credits WHERE status='available' ORDER BY expires_at"
        ).fetchall()
        return [dict(row) for row in rows]

    def is_muted(self, credit_id: str) -> bool:
        row = self.db.execute(
            "SELECT muted FROM mutes WHERE credit_id=?",
            (credit_id,),
        ).fetchone()
        return bool(row and row["muted"])

    def set_muted(self, credit_id: str, muted: bool) -> None:
        if muted:
            self.db.execute(
                """
                INSERT INTO mutes(credit_id, muted)
                VALUES(?, 1)
                ON CONFLICT(credit_id) DO UPDATE SET muted=1
                """,
                (credit_id,),
            )
        else:
            self.db.execute(
                "DELETE FROM mutes WHERE credit_id=?",
                (credit_id,),
            )
        self.db.commit()

    def attempt(self, credit_id: str, slot: int):
        return self.db.execute(
            """
            SELECT * FROM attempts
            WHERE credit_id=? AND slot_seconds=?
            """,
            (credit_id, slot),
        ).fetchone()

    def pending_attempt(self, credit_id: str):
        return self.db.execute(
            """
            SELECT * FROM attempts
            WHERE credit_id=? AND outcome IS NULL
            ORDER BY created_at DESC
            LIMIT 1
            """,
            (credit_id,),
        ).fetchone()

    def create_attempt(self, credit_id: str, slot: int):
        self.db.execute(
            """
            INSERT INTO attempts(
                credit_id, slot_seconds, idempotency_key, created_at
            )
            VALUES(?, ?, ?, ?)
            """,
            (credit_id, slot, str(uuid.uuid4()), int(time.time())),
        )
        self.db.commit()
        return self.attempt(credit_id, slot)

    def update_attempt(
        self,
        credit_id: str,
        slot: int,
        *,
        outcome: str | None = None,
        error: str | None = None,
        retry: bool = False,
    ) -> None:
        self.db.execute(
            """
            UPDATE attempts
            SET
                last_try_at=?,
                outcome=COALESCE(?, outcome),
                error=?,
                network_retries=network_retries+?
            WHERE credit_id=? AND slot_seconds=?
            """,
            (
                int(time.time()),
                outcome,
                error,
                1 if retry else 0,
                credit_id,
                slot,
            ),
        )
        self.db.commit()

    def attempts_for(self, credit_id: str) -> list[dict[str, Any]]:
        rows = self.db.execute(
            """
            SELECT * FROM attempts
            WHERE credit_id=?
            ORDER BY created_at
            """,
            (credit_id,),
        ).fetchall()
        return [dict(row) for row in rows]

    def has_terminal_attempt(self, credit_id: str) -> bool:
        return any(
            attempt.get("outcome") in {"reset", "alreadyRedeemed", "noCredit"}
            for attempt in self.attempts_for(credit_id)
        )

    def event_was_sent(self, dedupe_key: str) -> bool:
        row = self.db.execute(
            "SELECT 1 FROM sent_events WHERE dedupe_key=?",
            (dedupe_key,),
        ).fetchone()
        return row is not None

    def mark_event_sent(self, dedupe_key: str) -> None:
        self.db.execute(
            """
            INSERT OR IGNORE INTO sent_events(dedupe_key, sent_at)
            VALUES(?, ?)
            """,
            (dedupe_key, int(time.time())),
        )
        self.db.commit()

    def queue_notification(self, event: dict[str, Any]) -> None:
        key = str(event["dedupe_key"])
        payload = json.dumps(event, separators=(",", ":"), ensure_ascii=False)
        self.db.execute(
            """
            INSERT OR IGNORE INTO notification_outbox(
                dedupe_key, event_json, created_at
            )
            VALUES(?, ?, ?)
            """,
            (key, payload, int(time.time())),
        )
        self.db.commit()

    def pending_notifications(self) -> list[dict[str, Any]]:
        rows = self.db.execute(
            """
            SELECT event_json FROM notification_outbox
            ORDER BY created_at, dedupe_key
            """
        ).fetchall()
        return [json.loads(row["event_json"]) for row in rows]

    def mark_notification_failed(self, dedupe_key: str, error: str) -> None:
        self.db.execute(
            """
            UPDATE notification_outbox
            SET last_attempt_at=?, last_error=?
            WHERE dedupe_key=?
            """,
            (int(time.time()), error[:2000], dedupe_key),
        )
        self.db.commit()

    def remove_pending_notification(self, dedupe_key: str) -> None:
        self.db.execute(
            "DELETE FROM notification_outbox WHERE dedupe_key=?",
            (dedupe_key,),
        )
        self.db.commit()

    def preflight_done(self, credit_id: str) -> bool:
        row = self.db.execute(
            "SELECT preflight_done FROM credits WHERE id=?",
            (credit_id,),
        ).fetchone()
        return bool(row and row["preflight_done"])

    def mark_preflight(self, credit_id: str) -> None:
        self.db.execute(
            "UPDATE credits SET preflight_done=1 WHERE id=?",
            (credit_id,),
        )
        self.db.commit()

    def log(self, level: str, event: str, details: str = "") -> None:
        self.db.execute(
            """
            INSERT INTO events(ts, level, event, details)
            VALUES(?, ?, ?, ?)
            """,
            (int(time.time()), level, event, details[:2000]),
        )
        self.db.commit()

    def recent_events(self, limit: int = 50) -> list[dict[str, Any]]:
        limit = max(1, min(int(limit), 500))
        rows = self.db.execute(
            """
            SELECT ts, level, event, details
            FROM events
            ORDER BY id DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
        return [dict(row) for row in rows]

    def reminder_state(self, credit_id: str) -> dict[str, Any] | None:
        row = self.db.execute(
            "SELECT * FROM reminder_state WHERE credit_id=?",
            (credit_id,),
        ).fetchone()
        return dict(row) if row else None

    def set_reminder_state(
        self,
        credit_id: str,
        remaining: int,
        eligibility: bool | None,
    ) -> None:
        encoded = None if eligibility is None else int(eligibility)
        self.db.execute(
            """
            INSERT INTO reminder_state(
                credit_id, remaining_seconds, eligibility, updated_at
            )
            VALUES(?, ?, ?, ?)
            ON CONFLICT(credit_id) DO UPDATE SET
                remaining_seconds=excluded.remaining_seconds,
                eligibility=excluded.eligibility,
                updated_at=excluded.updated_at
            """,
            (credit_id, remaining, encoded, int(time.time())),
        )
        self.db.commit()
