"""Append-only SQLite event store. Every event that crosses the bus is kept, in order."""
from __future__ import annotations

import json
import sqlite3
import threading


class EventStore:
    def __init__(self, path=":memory:"):
        self._db = sqlite3.connect(path, check_same_thread=False)
        self._lock = threading.Lock()
        self._db.execute(
            "CREATE TABLE IF NOT EXISTS events ("
            " seq INTEGER PRIMARY KEY AUTOINCREMENT, type TEXT NOT NULL, ts REAL NOT NULL, body TEXT NOT NULL)"
        )
        self._db.execute("CREATE INDEX IF NOT EXISTS events_type ON events(type, seq)")
        self._db.commit()

    def append(self, event: dict) -> int:
        with self._lock:
            cur = self._db.execute("INSERT INTO events(type, ts, body) VALUES (?, ?, ?)",
                                   (event["type"], event["ts"], json.dumps(event)))
            self._db.commit()
            return cur.lastrowid

    def query(self, type_=None, after_seq=0, limit=1000):
        sql, args = "SELECT seq, body FROM events WHERE seq > ?", [after_seq]
        if type_:
            sql += " AND type = ?"
            args.append(type_)
        sql += " ORDER BY seq LIMIT ?"
        args.append(limit)
        with self._lock:
            return [{"seq": s, **json.loads(b)} for s, b in self._db.execute(sql, args)]

    def snapshot(self):
        """What a freshly connected dashboard needs, oldest first: the latest map, the last
        telemetry per drone, and the latest state of every detection (plus its confirm)."""
        sql = """
            SELECT seq, body FROM events WHERE seq IN (
                SELECT MAX(seq) FROM events WHERE type = 'map_update'
                UNION SELECT MAX(seq) FROM events WHERE type = 'telemetry' GROUP BY json_extract(body, '$.drone')
                UNION SELECT MAX(seq) FROM events WHERE type IN ('detection', 'confirm')
                      GROUP BY type, json_extract(body, '$.id')
            ) ORDER BY seq"""
        with self._lock:
            return [json.loads(b) for _, b in self._db.execute(sql)]

    def latest_detection(self, det_id: int):
        with self._lock:
            row = self._db.execute(
                "SELECT body FROM events WHERE type = 'detection' AND json_extract(body, '$.id') = ? "
                "ORDER BY seq DESC LIMIT 1", (det_id,)).fetchone()
        return json.loads(row[0]) if row else None
