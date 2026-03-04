from __future__ import annotations

import os
import sqlite3
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DB_PATH = Path(os.getenv("DB_PATH", ROOT / "backend" / "app.db"))


def db_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def migrate() -> None:
    with db_conn() as conn:
        for migration in sorted((ROOT / "backend" / "migrations").glob("*.sql")):
            conn.executescript(migration.read_text())
