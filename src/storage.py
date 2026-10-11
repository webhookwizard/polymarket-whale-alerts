"""SQLite persistence: watchers, alerts, paper positions, TG chat flags."""
from __future__ import annotations

import json
import sqlite3
import time

from .models import PaperPosition, WatcherConfig


class Storage:
    def __init__(self, path: str = "whale_alerts.db") -> None:
        self.path = path
        self.conn = sqlite3.connect(path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self._init_schema()

    def _init_schema(self) -> None:
        self.conn.executescript("""
        CREATE TABLE IF NOT EXISTS watchers (
            name TEXT PRIMARY KEY,
            min_usd REAL NOT NULL,
            prob_min REAL NOT NULL,
            prob_max REAL NOT NULL,
            allow_slugs TEXT NOT NULL DEFAULT '[]',
            block_slugs TEXT NOT NULL DEFAULT '[]',
            enabled INTEGER NOT NULL DEFAULT 1
        );
        CREATE TABLE IF NOT EXISTS alerts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            watcher_name TEXT NOT NULL,
            tx_hash TEXT NOT NULL UNIQUE,
            market_title TEXT NOT NULL,
            market_slug TEXT NOT NULL DEFAULT '',
            side TEXT NOT NULL,
            outcome TEXT NOT NULL,
            size_usd REAL NOT NULL,
            price REAL NOT NULL,
            detected_at INTEGER NOT NULL
        );
        CREATE TABLE IF NOT EXISTS paper_positions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            market_title TEXT NOT NULL,
            market_slug TEXT NOT NULL DEFAULT '',
            token_id TEXT NOT NULL DEFAULT '',
            side TEXT NOT NULL,
            outcome TEXT NOT NULL,
            entry_price REAL NOT NULL,
            size_usd REAL NOT NULL,
            opened_at INTEGER NOT NULL,
            closed_at INTEGER NOT NULL DEFAULT 0,
            exit_price REAL NOT NULL DEFAULT 0,
            status TEXT NOT NULL DEFAULT 'open'
        );
        CREATE TABLE IF NOT EXISTS tg_chats (
            chat_id TEXT PRIMARY KEY,
            live_enabled INTEGER NOT NULL DEFAULT 0,
            updated_at INTEGER NOT NULL
        );
        """)
        self.conn.commit()

    # -- watchers --------------------------------------------------------
    def save_watcher(self, w: WatcherConfig) -> None:
        self.conn.execute(
            """INSERT INTO watchers(name,min_usd,prob_min,prob_max,
                                    allow_slugs,block_slugs,enabled)
               VALUES(?,?,?,?,?,?,?)
               ON CONFLICT(name) DO UPDATE SET
                 min_usd=excluded.min_usd, prob_min=excluded.prob_min,
                 prob_max=excluded.prob_max, allow_slugs=excluded.allow_slugs,
                 block_slugs=excluded.block_slugs, enabled=excluded.enabled""",
            (w.name, w.min_usd, w.prob_min, w.prob_max,
             json.dumps(w.allow_slugs), json.dumps(w.block_slugs),
             1 if w.enabled else 0),
        )
        self.conn.commit()

    def list_watchers(self) -> list[WatcherConfig]:
        rows = self.conn.execute("SELECT * FROM watchers ORDER BY name").fetchall()
        return [
            WatcherConfig(
                name=r["name"], min_usd=r["min_usd"],
                prob_min=r["prob_min"], prob_max=r["prob_max"],
                allow_slugs=json.loads(r["allow_slugs"]),
                block_slugs=json.loads(r["block_slugs"]),
                enabled=bool(r["enabled"]),
            )
            for r in rows
        ]

    def delete_watcher(self, name: str) -> bool:
        cur = self.conn.execute("DELETE FROM watchers WHERE name=?", (name,))
        self.conn.commit()
        return cur.rowcount > 0

    # -- alerts ----------------------------------------------------------
    def save_alert(self, watcher_name: str, tx_hash: str, market_title: str,
                   market_slug: str, side: str, outcome: str,
                   size_usd: float, price: float) -> bool:
        """Returns False if this tx was already recorded (dedupe)."""
        try:
            self.conn.execute(
                """INSERT INTO alerts(watcher_name,tx_hash,market_title,market_slug,
                                      side,outcome,size_usd,price,detected_at)
                   VALUES(?,?,?,?,?,?,?,?,?)""",
                (watcher_name, tx_hash, market_title, market_slug, side,
                 outcome, size_usd, price, int(time.time())),
            )
            self.conn.commit()
            return True
        except sqlite3.IntegrityError:
            return False

    def recent_alerts(self, limit: int = 50) -> list[dict]:
        rows = self.conn.execute(
            "SELECT * FROM alerts ORDER BY id DESC LIMIT ?", (limit,)
        ).fetchall()
        return [dict(r) for r in rows]

    # -- paper positions --------------------------------------------------
    def open_paper_position(self, p: PaperPosition) -> int:
        cur = self.conn.execute(
            """INSERT INTO paper_positions(market_title,market_slug,token_id,side,
                                           outcome,entry_price,size_usd,opened_at,status)
               VALUES(?,?,?,?,?,?,?,?,?)""",
            (p.market_title, p.market_slug, p.token_id, p.side, p.outcome,
             p.entry_price, p.size_usd, p.opened_at or int(time.time()), "open"),
        )
        self.conn.commit()
        return cur.lastrowid

    def close_paper_position(self, pos_id: int, exit_price: float) -> bool:
        cur = self.conn.execute(
            """UPDATE paper_positions SET status='closed', closed_at=?,
               exit_price=? WHERE id=? AND status='open'""",
            (int(time.time()), exit_price, pos_id),
        )
        self.conn.commit()
        return cur.rowcount > 0

    def get_position(self, pos_id: int) -> PaperPosition | None:
        r = self.conn.execute(
            "SELECT * FROM paper_positions WHERE id=?", (pos_id,)).fetchone()
        return self._row_to_position(r) if r else None

    def list_positions(self, status: str | None = None) -> list[PaperPosition]:
        q = "SELECT * FROM paper_positions ORDER BY id DESC"
        params: tuple = ()
        if status:
            q = "SELECT * FROM paper_positions WHERE status=? ORDER BY id DESC"
            params = (status,)
        return [self._row_to_position(r)
                for r in self.conn.execute(q, params).fetchall()]

    @staticmethod
    def _row_to_position(r: sqlite3.Row) -> PaperPosition:
        return PaperPosition(
            id=r["id"], market_title=r["market_title"],
            market_slug=r["market_slug"], token_id=r["token_id"],
            side=r["side"], outcome=r["outcome"],
            entry_price=r["entry_price"], size_usd=r["size_usd"],
            opened_at=r["opened_at"], closed_at=r["closed_at"],
            exit_price=r["exit_price"], status=r["status"],
        )

    # -- TG chat flags ----------------------------------------------------
    def set_chat_live(self, chat_id: str, enabled: bool) -> None:
        self.conn.execute(
            """INSERT INTO tg_chats(chat_id,live_enabled,updated_at)
               VALUES(?,?,?)
               ON CONFLICT(chat_id) DO UPDATE SET
                 live_enabled=excluded.live_enabled,
                 updated_at=excluded.updated_at""",
            (str(chat_id), 1 if enabled else 0, int(time.time())),
        )
        self.conn.commit()

    def chat_live_enabled(self, chat_id: str) -> bool:
        r = self.conn.execute(
            "SELECT live_enabled FROM tg_chats WHERE chat_id=?",
            (str(chat_id),)).fetchone()
        return bool(r and r["live_enabled"])

    def close(self) -> None:
        self.conn.close()
