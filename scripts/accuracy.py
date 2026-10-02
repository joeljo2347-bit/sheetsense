"""How often the model's answer matches a hand-written query, on the example files.

    python3 scripts/accuracy.py                 # with the default model
    python3 scripts/accuracy.py --model qwen3:8b --runs 3
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from sheetsense import guard  # noqa: E402
from sheetsense.ask import CouldNotAnswer, ask  # noqa: E402
from sheetsense.model import DEFAULT_MODEL, Ollama  # noqa: E402
from sheetsense.tables import load, open_db  # noqa: E402

EXAMPLES = Path(__file__).resolve().parent.parent / "examples"
FILES = [EXAMPLES / "sales_2025.xlsx", EXAMPLES / "webinar_attendance.csv"]

CASES = [
    ("What were total sales in 2025?", "SELECT SUM(amount) FROM sales_2025"),
    ("How much is unpaid, by rep?", "SELECT rep, SUM(amount) FROM sales_2025 WHERE status = 'Unpaid' GROUP BY rep"),
    ("Which region sold the most in Q3, and how much?",
     "SELECT region, SUM(amount) s FROM sales_2025 WHERE date BETWEEN '2025-07-01' AND '2025-09-30' GROUP BY region ORDER BY s DESC LIMIT 1"),
    ("Total sales month by month.", "SELECT substr(date, 1, 7), SUM(amount) FROM sales_2025 GROUP BY 1"),
    ("Which customers attended a webinar but never placed an order?",
     "SELECT DISTINCT customer FROM webinar_attendance WHERE attended = 'Yes' AND customer NOT IN (SELECT customer FROM sales_2025)"),
    ("What are the top 3 products by revenue?", "SELECT product, SUM(amount) s FROM sales_2025 GROUP BY product ORDER BY s DESC LIMIT 3"),
    ("How many orders did Blue Harbor Dental place?", "SELECT COUNT(*) FROM sales_2025 WHERE customer = 'Blue Harbor Dental'"),
    ("What's the average order amount for standing desks?", "SELECT AVG(amount) FROM sales_2025 WHERE product = 'Standing desk'"),
]


def values(rows) -> list:
    """The answer's values, rounded and order-free, so labels and column order don't matter."""
    out = []
    for row in rows:
        for v in row:
            out.append(round(v, 2) if isinstance(v, float) else (str(v).lower() if v is not None else None))
    return sorted(out, key=str)


def matches(expected, got) -> bool:
    want, have = values(expected), values(got)
    return all(w in have for w in want) and len(have) <= len(want) * 2


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--runs", type=int, default=1)
    args = parser.parse_args()

    db = open_db()
    tables = load(db, FILES)
    model = Ollama(args.model)
    passed = total = 0
    started = time.monotonic()
    for question, reference in CASES:
        expected = guard.run(db, reference).rows
        for _ in range(args.runs):
            total += 1
            try:
                got = ask(question, db, tables, model).result.rows
                ok = matches(expected, got)
            except (CouldNotAnswer, ConnectionError) as e:
                ok = False
                print(f"      {e}")
            passed += ok
            print(f"{'PASS' if ok else 'FAIL'}  {question}")
    print(f"\n{passed}/{total} correct with {args.model}, {(time.monotonic() - started) / total:.1f} s a question")
    return 0 if passed == total else 1


if __name__ == "__main__":
    raise SystemExit(main())
