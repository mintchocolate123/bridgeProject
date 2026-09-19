"""SQLite 持久化。

房間狀態整份存成 JSON(Room.to_dict),事件逐筆附加。伺服器重啟時把
兩者讀回來,用 Room.from_dict 還原。

只用標準函式庫的 sqlite3,不需要另外架資料庫。平台是單一事件迴圈,
所有存取都在同一個執行緒,不需要鎖。
"""

import json
import os
import sqlite3
import time

_SCHEMA = """
CREATE TABLE IF NOT EXISTS rooms (
    code        TEXT PRIMARY KEY,
    status      TEXT NOT NULL,
    data        TEXT NOT NULL,
    updated_at  REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS events (
    room_code   TEXT NOT NULL,
    seq         INTEGER NOT NULL,
    data        TEXT NOT NULL,
    PRIMARY KEY (room_code, seq)
);
"""


class Store:
    def __init__(self, path):
        if path != ":memory:":
            os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
        self.conn = sqlite3.connect(path, check_same_thread=False)
        self.conn.execute("PRAGMA journal_mode=WAL")
        self.conn.executescript(_SCHEMA)
        self.conn.commit()

    def save(self, room, events_from=0):
        """存房間狀態,並附加序號 >= events_from 的事件。"""
        with self.conn:
            self.conn.execute(
                "INSERT INTO rooms (code, status, data, updated_at) VALUES (?, ?, ?, ?) "
                "ON CONFLICT(code) DO UPDATE SET status=excluded.status, "
                "data=excluded.data, updated_at=excluded.updated_at",
                (room.code, room.status, json.dumps(room.to_dict(), ensure_ascii=False),
                 time.time()))
            self.conn.executemany(
                "INSERT OR IGNORE INTO events (room_code, seq, data) VALUES (?, ?, ?)",
                [(room.code, e["seq"], json.dumps(e, ensure_ascii=False))
                 for e in room.events[events_from:]])

    def load_all(self):
        """回傳 [(room_data, events), ...]。"""
        rows = self.conn.execute("SELECT code, data FROM rooms").fetchall()
        result = []
        for code, data in rows:
            events = [json.loads(d) for (d,) in self.conn.execute(
                "SELECT data FROM events WHERE room_code = ? ORDER BY seq", (code,))]
            result.append((json.loads(data), events))
        return result

    def exists(self, code):
        return self.conn.execute("SELECT 1 FROM rooms WHERE code = ?", (code,)).fetchone() is not None

    def close(self):
        self.conn.close()
