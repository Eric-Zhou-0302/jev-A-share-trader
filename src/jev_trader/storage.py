from __future__ import annotations

import json
import sqlite3
import time
import zlib
from contextlib import contextmanager
from pathlib import Path


class Store:
    def __init__(self, directory: Path):
        directory.mkdir(parents=True, exist_ok=True)
        self.path = directory / "market.sqlite3"
        with self.connect() as db:
            db.executescript("""
                PRAGMA journal_mode=WAL;
                CREATE TABLE IF NOT EXISTS cache (key TEXT PRIMARY KEY, value BLOB NOT NULL, updated REAL);
                CREATE TABLE IF NOT EXISTS analyses (id TEXT PRIMARY KEY, symbol TEXT, as_of TEXT, created REAL, value BLOB NOT NULL);
                CREATE INDEX IF NOT EXISTS analyses_symbol ON analyses(symbol, created DESC);
                CREATE TABLE IF NOT EXISTS analysis_summaries (id TEXT PRIMARY KEY, value BLOB NOT NULL);
                CREATE TABLE IF NOT EXISTS watchlist (symbol TEXT PRIMARY KEY, name TEXT, created REAL);
                CREATE TABLE IF NOT EXISTS jobs (id TEXT PRIMARY KEY, created REAL, value BLOB NOT NULL);
            """)

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.path, timeout=30)
        try:
            yield db
            db.commit()
        finally:
            db.close()

    @staticmethod
    def pack(value) -> bytes:
        return zlib.compress(json.dumps(value, ensure_ascii=False, allow_nan=False).encode())

    @staticmethod
    def unpack(value: bytes):
        return json.loads(zlib.decompress(value))

    def get(self, key: str, max_age: float | None = None):
        with self.connect() as db:
            row = db.execute("SELECT value, updated FROM cache WHERE key=?", (key,)).fetchone()
        if row and (max_age is None or time.time() - row[1] <= max_age):
            return self.unpack(row[0])
        return None

    def put(self, key: str, value) -> None:
        with self.connect() as db:
            db.execute("INSERT OR REPLACE INTO cache VALUES(?,?,?)", (key, self.pack(value), time.time()))

    def save_analysis(self, value: dict) -> None:
        with self.connect() as db:
            db.execute("INSERT OR REPLACE INTO analyses VALUES(?,?,?,?,?)", (value["id"], value["symbol"], value["as_of"], time.time(), self.pack(value)))
            summary = {key: value[key] for key in ("id", "symbol", "name", "as_of", "status", "action", "horizon", "created_at")}
            db.execute("INSERT OR REPLACE INTO analysis_summaries VALUES(?,?)", (value["id"], self.pack(summary)))

    def analysis(self, identifier: str) -> dict | None:
        with self.connect() as db:
            row = db.execute("SELECT value FROM analyses WHERE id=?", (identifier,)).fetchone()
        return self.unpack(row[0]) if row else None

    def history(self, symbol: str | None = None, limit: int = 100) -> list[dict]:
        with self.connect() as db:
            rows = db.execute("SELECT value FROM analyses " + ("WHERE symbol=? " if symbol else "") + "ORDER BY created DESC LIMIT ?", ((symbol, limit) if symbol else (limit,))).fetchall()
        return [self.unpack(row[0]) for row in rows]

    def watchlist(self) -> list[dict]:
        with self.connect() as db:
            rows = db.execute("SELECT symbol, name FROM watchlist ORDER BY created").fetchall()
        return [{"symbol": row[0], "name": row[1]} for row in rows]

    def summaries(self, symbol: str | None = None, limit: int = 100) -> list[dict]:
        # 列表不读取数万点图表数据；旧记录仅在首次读取时补齐摘要。
        with self.connect() as db:
            rows = db.execute("SELECT a.id, s.value FROM analyses a LEFT JOIN analysis_summaries s ON s.id=a.id " + ("WHERE a.symbol=? " if symbol else "") + "ORDER BY a.created DESC LIMIT ?", ((symbol, limit) if symbol else (limit,))).fetchall()
            results = []
            for identifier, summary in rows:
                if summary is None:
                    full = self.unpack(db.execute("SELECT value FROM analyses WHERE id=?", (identifier,)).fetchone()[0])
                    summary = self.pack({key: full[key] for key in ("id", "symbol", "name", "as_of", "status", "action", "horizon", "created_at")})
                    db.execute("INSERT OR REPLACE INTO analysis_summaries VALUES(?,?)", (identifier, summary))
                results.append(self.unpack(summary))
        return results

    def watch(self, symbol: str, name: str, remove: bool = False):
        with self.connect() as db:
            if remove:
                db.execute("DELETE FROM watchlist WHERE symbol=?", (symbol,))
            else:
                db.execute("INSERT OR IGNORE INTO watchlist VALUES(?,?,?)", (symbol, name, time.time()))

    def search_summaries(self, query="", date_from=None, date_to=None, page=0, limit=50):
        # 只扫描轻量摘要；搜索覆盖全部历史，不受侧栏最近 100 条的限制。
        query = query.strip().casefold()
        matches = [item for item in self.summaries(limit=-1)
                   if (not query or query in f"{item['symbol']} {item['name']}".casefold())
                   and (not date_from or item["as_of"] >= date_from)
                   and (not date_to or item["as_of"] <= date_to)]
        total = len(matches)
        page = min(page, max(0, (total - 1) // limit))
        return {"items": matches[page * limit:(page + 1) * limit], "total": total, "page": page, "limit": limit}

    def save_job(self, value: dict):
        with self.connect() as db:
            db.execute("INSERT OR REPLACE INTO jobs VALUES(?,?,?)", (value["id"], value["created"], self.pack(value)))

    def jobs(self) -> list[dict]:
        with self.connect() as db:
            rows = db.execute("SELECT value FROM jobs ORDER BY created DESC LIMIT 50").fetchall()
        return [self.unpack(row[0]) for row in rows]

    def job(self, identifier: str) -> dict | None:
        with self.connect() as db:
            row = db.execute("SELECT value FROM jobs WHERE id=?", (identifier,)).fetchone()
        return self.unpack(row[0]) if row else None
