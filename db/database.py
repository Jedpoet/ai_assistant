import sqlite3
import os
from pathlib import Path

DB_PATH = os.getenv("DB_PATH", "data/family.db")


def get_conn() -> sqlite3.Connection:
    Path(DB_PATH).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    """建立所有資料表"""
    with get_conn() as conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS members (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                discord_id  TEXT UNIQUE NOT NULL,
                name        TEXT NOT NULL,
                role        TEXT,                  -- 例如 "爸爸", "媽媽", "小孩"
                color       TEXT DEFAULT '#4A90D9', -- 週行程圖的顏色
                preferences TEXT DEFAULT '',        -- 自然語言偏好，塞進 prompt 用
                calendar_id TEXT,                  -- Google Calendar ID
                created_at  TEXT DEFAULT (datetime('now'))
            );

            CREATE TABLE IF NOT EXISTS fixed_schedules (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                member_id   INTEGER NOT NULL REFERENCES members(id),
                title       TEXT NOT NULL,
                day_of_week INTEGER NOT NULL,  -- 0=週一 ... 6=週日
                start_time  TEXT NOT NULL,     -- "HH:MM"
                end_time    TEXT NOT NULL,     -- "HH:MM"
                note        TEXT DEFAULT ''
            );
        """)


# ── Members ──────────────────────────────────────────────

def upsert_member(discord_id: str, name: str, role: str = "", color: str = "#4A90D9") -> int:
    with get_conn() as conn:
        conn.execute("""
            INSERT INTO members (discord_id, name, role, color)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(discord_id) DO UPDATE SET
                name  = excluded.name,
                role  = excluded.role,
                color = excluded.color
        """, (discord_id, name, role, color))
        row = conn.execute("SELECT id FROM members WHERE discord_id=?", (discord_id,)).fetchone()
        return row["id"]


def get_member(discord_id: str) -> sqlite3.Row | None:
    with get_conn() as conn:
        return conn.execute(
            "SELECT * FROM members WHERE discord_id=?", (discord_id,)
        ).fetchone()


def get_member_by_name(name: str) -> sqlite3.Row | None:
    """以名字查詢家人（模糊比對，不分大小寫）"""
    with get_conn() as conn:
        return conn.execute(
            "SELECT * FROM members WHERE name=? COLLATE NOCASE", (name,)
        ).fetchone()


def get_all_members() -> list[sqlite3.Row]:
    with get_conn() as conn:
        return conn.execute("SELECT * FROM members ORDER BY id").fetchall()


def update_preferences(discord_id: str, preferences: str):
    with get_conn() as conn:
        conn.execute(
            "UPDATE members SET preferences=? WHERE discord_id=?",
            (preferences, discord_id)
        )


def update_calendar_id(discord_id: str, calendar_id: str):
    with get_conn() as conn:
        conn.execute(
            "UPDATE members SET calendar_id=? WHERE discord_id=?",
            (calendar_id, discord_id)
        )


# ── Fixed Schedules ──────────────────────────────────────

def add_fixed_schedule(member_id: int, title: str, day_of_week: int,
                        start_time: str, end_time: str, note: str = ""):
    with get_conn() as conn:
        conn.execute("""
            INSERT INTO fixed_schedules (member_id, title, day_of_week, start_time, end_time, note)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (member_id, title, day_of_week, start_time, end_time, note))


def get_fixed_schedules(member_id: int) -> list[sqlite3.Row]:
    with get_conn() as conn:
        return conn.execute(
            "SELECT * FROM fixed_schedules WHERE member_id=? ORDER BY day_of_week, start_time",
            (member_id,)
        ).fetchall()


def delete_fixed_schedule(schedule_id: int):
    with get_conn() as conn:
        conn.execute("DELETE FROM fixed_schedules WHERE id=?", (schedule_id,))
