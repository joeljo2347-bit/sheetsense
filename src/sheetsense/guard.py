"""What may run, and the query mistakes worth catching before they become wrong answers."""

from __future__ import annotations

import re
import sqlite3
from dataclasses import dataclass
from typing import List, Optional, Sequence

from .tables import Table

WRITES = re.compile(
    r"\b(attach|detach|pragma|vacuum|load_extension)\b|\b(insert|replace)\s+into\b|"
    r"\bupdate\s+\w+\s+set\b|\bdelete\s+from\b|\b(drop|alter)\s+table\b|\bcreate\s+(table|view|index|trigger)\b",
    re.IGNORECASE,
)
TEXT_SURGERY = re.compile(r"\b(substr|substring|ltrim|rtrim|trim)\s*\(\s*(?:\w+\.)?[\"`\[]?(\w+)[\"`\]]?\s*[,)]", re.IGNORECASE)


def refuse(sql: str) -> Optional[str]:
    """Why this SQL may not run, or None. One SELECT (or WITH … SELECT), nothing that writes."""
    s = re.sub(r"--[^\n]*|/\*.*?\*/", " ", sql, flags=re.DOTALL).strip().rstrip(";").strip()
    if not re.match(r"^(select|with)\b", s, re.IGNORECASE):
        return "Only a SELECT query (or WITH … SELECT) can run."
    if ";" in s:
        return "One query at a time."
    if WRITES.search(s):
        return "The query can only read the tables."
    return None


def misread(sql: str, tables: Sequence[Table]) -> Optional[str]:
    """Text functions on a column that is already a number.

    A model asked for totals often writes SUM(CAST(SUBSTR(total, 2) AS REAL)) to strip a "$"
    that was removed on load, which quietly cuts the first digit off every value.
    """
    numbers = {c.name.lower() for t in tables for c in t.columns if c.kind == "number"}
    for m in TEXT_SURGERY.finditer(sql):
        if m.group(2).lower() in numbers:
            return f"{m.group(2)} is already a number ($ signs and commas were removed on load): use it as it is, without {m.group(1).upper()}."
    return None


@dataclass
class Result:
    columns: List[str]
    rows: List[tuple]
    cut: bool = False


def run(db: sqlite3.Connection, sql: str, limit: int = 500, seconds: float = 10.0) -> Result:
    """Run one read-only query, stopping it after a few seconds."""
    import time

    deadline = time.monotonic() + seconds
    db.set_progress_handler(lambda: 1 if time.monotonic() > deadline else 0, 10_000)
    db.execute("PRAGMA query_only = ON")
    try:
        cur = db.execute(sql)
        rows = cur.fetchmany(limit + 1)
        columns = [d[0] for d in cur.description or []]
    finally:
        db.set_progress_handler(None, 0)
    return Result(columns, rows[:limit], cut=len(rows) > limit)
