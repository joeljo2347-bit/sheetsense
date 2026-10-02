"""sheetsense: ask your spreadsheets questions, get exact answers.

    sheetsense describe examples/sales_2025.xlsx
    sheetsense ask examples/sales_2025.xlsx "Which region sold the most in Q3?"
    sheetsense sql examples/sales_2025.xlsx "SELECT region, SUM(amount) FROM sales_2025 GROUP BY region"
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import List, Sequence

from . import __version__, guard
from .ask import CouldNotAnswer, ask
from .model import DEFAULT_MODEL, Ollama
from .tables import describe, load, open_db


def fmt(value) -> str:
    if value is None:
        return ""
    if isinstance(value, float):
        return f"{value:,.2f}" if value != int(value) or abs(value) >= 1000 else f"{int(value)}"
    return str(value)


def table(result: guard.Result, limit: int = 50) -> str:
    rows = [[fmt(v) for v in r] for r in result.rows[:limit]]
    widths = [max([len(c)] + [len(r[i]) for r in rows]) for i, c in enumerate(result.columns)]
    numeric = [all(isinstance(r[i], (int, float)) or r[i] is None for r in result.rows) for i in range(len(result.columns))]

    def line(cells: Sequence[str]) -> str:
        return "  ".join(c.rjust(w) if n else c.ljust(w) for c, w, n in zip(cells, widths, numeric)).rstrip()

    out = [line(result.columns), "  ".join("─" * w for w in widths)] + [line(r) for r in rows]
    more = len(result.rows) - limit
    if more > 0 or result.cut:
        out.append(f"… {'more' if result.cut else more} more rows")
    return "\n".join(out)


def files(paths: List[str]) -> List[Path]:
    found = []
    for p in paths:
        path = Path(p).expanduser()
        if not path.exists():
            sys.exit(f"sheetsense: no such file: {p}")
        if path.suffix.lower() not in (".xlsx", ".xlsm", ".csv"):
            sys.exit(f"sheetsense: {p} isn't an .xlsx or .csv file")
        found.append(path)
    return found


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="sheetsense", description="Ask your spreadsheets questions; get exact answers.")
    parser.add_argument("--version", action="version", version=f"sheetsense {__version__}")
    sub = parser.add_subparsers(dest="command", required=True)

    p_desc = sub.add_parser("describe", help="show the tables a question can use")
    p_desc.add_argument("files", nargs="+")

    p_ask = sub.add_parser("ask", help="ask a question in plain English")
    p_ask.add_argument("files", nargs="+", help="spreadsheets, then the question last")
    p_ask.add_argument("--model", default=DEFAULT_MODEL, help=f"Ollama model (default {DEFAULT_MODEL})")
    p_ask.add_argument("--quiet", action="store_true", help="the answer only, without the SQL")

    p_sql = sub.add_parser("sql", help="run your own SELECT")
    p_sql.add_argument("files", nargs="+", help="spreadsheets, then the SQL last")

    args = parser.parse_args(argv)
    db = open_db()

    if args.command == "describe":
        print(describe(load(db, files(args.files))))
        return 0

    if len(args.files) < 2:
        parser.error("give at least one file and then the question or SQL")
    *paths, text = args.files
    tables = load(db, files(paths))
    if not tables:
        sys.exit("sheetsense: no sheet has a row of headings over its data")

    if args.command == "sql":
        why = guard.refuse(text) or guard.misread(text, tables)
        if why:
            sys.exit(f"sheetsense: {why}")
        print(table(guard.run(db, text)))
        return 0

    try:
        answer = ask(text, db, tables, Ollama(args.model))
    except (ConnectionError, CouldNotAnswer) as e:
        sys.exit(f"sheetsense: {e}")
    if not args.quiet:
        print(f"\033[2m{answer.sql}\033[0m\n" if sys.stdout.isatty() else f"{answer.sql}\n")
    print(table(answer.result))
    if answer.note and not args.quiet:
        print(f"\n{answer.note}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
