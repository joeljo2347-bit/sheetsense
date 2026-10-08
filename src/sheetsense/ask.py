"""Ask a question: the model writes the SQL, SQLite computes the answer, mistakes go back to the model."""

from __future__ import annotations

import json
import re
import sqlite3
from dataclasses import dataclass, field
from typing import List, Optional, Sequence

from . import guard
from .model import SYSTEM, Model
from .tables import Table, describe

MAX_TRIES = 3


@dataclass
class Answer:
    question: str
    sql: str
    note: str
    result: guard.Result
    attempts: List[str] = field(default_factory=list)  # what went wrong before it worked


class CouldNotAnswer(Exception):
    def __init__(self, message: str, attempts: List[str]):
        super().__init__(message)
        self.attempts = attempts


class NotInTheSheets(Exception):
    """The model wrote no SQL and said why: the sheets don't hold the answer. Asking again won't help."""

    def __init__(self, note: str):
        super().__init__(f"Can't answer from these sheets: {note}")
        self.note = note


def parse(reply: str) -> tuple[str, str]:
    """The SQL and note from the model's reply: JSON, or failing that a ```sql block."""
    try:
        data = json.loads(reply)
        return str(data.get("sql") or "").strip(), str(data.get("note") or "").strip()
    except (json.JSONDecodeError, AttributeError):
        block = re.search(r"```(?:sql)?\s*(.+?)```", reply, re.DOTALL | re.IGNORECASE)
        return (block.group(1).strip() if block else reply.strip()), ""


def problem(sql: str, tables: Sequence[Table]) -> Optional[str]:
    if not sql:
        return "The reply had no SQL."
    return guard.refuse(sql) or guard.misread(sql, tables)


def ask(question: str, db: sqlite3.Connection, tables: Sequence[Table], model: Model) -> Answer:
    messages = [
        {"role": "system", "content": SYSTEM + "\n\n" + describe(tables)},
        {"role": "user", "content": question},
    ]
    attempts: List[str] = []
    for _ in range(MAX_TRIES):
        reply = model.complete(messages)
        sql, note = parse(reply)
        if not sql and note:
            raise NotInTheSheets(note)
        why = problem(sql, tables)
        if why is None:
            try:
                return Answer(question, sql, note, guard.run(db, sql), attempts)
            except (sqlite3.Error, sqlite3.Warning) as e:  # on 3.9, "one statement" is a Warning
                why = f"SQLite: {e}"
        attempts.append(why)
        messages += [
            {"role": "assistant", "content": reply},
            {"role": "user", "content": f"That didn't work: {why}\nThe tables are:\n{describe(tables)}\nReply with corrected JSON."},
        ]
    raise CouldNotAnswer(f"No working query after {MAX_TRIES} tries: {attempts[-1]}", attempts)
