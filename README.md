# sheetsense

[![tests](https://github.com/joeljo2347-bit/sheetsense/actions/workflows/tests.yml/badge.svg)](https://github.com/joeljo2347-bit/sheetsense/actions/workflows/tests.yml)
![python](https://img.shields.io/badge/python-3.9%2B-blue)
![license](https://img.shields.io/badge/license-MIT-green)

Ask your spreadsheets questions in plain English and get **exact** answers, on your own computer.

```console
$ sheetsense ask examples/sales_2025.xlsx examples/webinar_attendance.csv \
    "Which customers attended a webinar but never placed an order?"

SELECT DISTINCT wa.customer AS "Customer"
FROM webinar_attendance wa
LEFT JOIN sales_2025 s ON wa.customer = s.customer
WHERE wa.attended = 'Yes'
  AND s.customer IS NULL;

Customer
─────────────────
Northgate Realty
Marlow Accounting
Oakhaven Vet
```

## Why

Language models are good at understanding a question and bad at arithmetic. Paste a few hundred
rows into a chatbot and ask for a total, and you'll get a confident number that's a little off,
or a list of names with one missing. For a sales report or a reconciliation, a little off is wrong.

sheetsense splits the work:

- **The model only writes the query.** It sees the tables' columns, never asked to add anything up.
- **SQLite computes every figure.** Sums, counts, averages and "in this list but not that one" come
  from the database, so they're exact.
- **Mistakes go back to the model, not to you.** A query that fails, or one that would give a
  wrong answer, is sent back with the reason, and the model fixes it (up to three tries).
- **Nothing leaves your computer.** It runs on a local model through [Ollama](https://ollama.com).
  No API keys, no uploads.

```mermaid
flowchart LR
    Q[Question] --> M[Local model<br/>writes one SELECT]
    F[.xlsx / .csv] --> L[Loader<br/>clean, typed tables] --> S[(SQLite<br/>in memory, read-only)]
    L -. schema .-> M
    M --> G{Guard}
    G -- "writes, bad SQL,<br/>common slips" --> M
    G -- ok --> S --> A[Exact answer<br/>+ the SQL]
```

## Real spreadsheets are messy

The loader handles what real exports look like, so the query sees clean columns:

| In the sheet | What sheetsense does |
| --- | --- |
| A title and blank rows above the headings | Finds the heading row |
| Money typed as text: `$1,216.50`, `(25.00)` | Reads it as a number (negative in brackets) |
| A **Total** row at the bottom | Leaves it out, so sums aren't doubled |
| `Unpaid`, `unpaid`, `UNPAID` | Matches them all: text compares ignoring case |
| Dates as dates, or as `03/09/2025` | Stores `2025-03-09`, so months group cleanly |
| A status or region column | Shows the model its few values, so it spells them right |
| Two columns with the same heading | Gives them distinct names |

The guard catches the model's most common slips before they become wrong answers. For example, a
model will often write `SUBSTR(amount, 2)` to strip a `$` that's already gone, which silently
drops the first digit of every amount. sheetsense refuses that query and tells the model why.

## Install

```bash
pip install git+https://github.com/joeljo2347-bit/sheetsense
ollama pull gpt-oss:20b        # or any model that writes SQL well
```

Python 3.9+ and one dependency (`openpyxl`).

## Use

```bash
sheetsense describe sales.xlsx                          # the tables and columns a question can use
sheetsense ask sales.xlsx "How much is unpaid, by rep?" # a question in plain English
sheetsense ask sales.xlsx leads.csv "Which leads never bought?"   # across files
sheetsense sql sales.xlsx "SELECT region, SUM(amount) FROM sales GROUP BY region"
```

`--model` picks another Ollama model (or set `SHEETSENSE_MODEL`); `--quiet` prints only the answer.

## Accuracy

`scripts/accuracy.py` asks eight questions about the example files and compares each answer with a
hand-written query: totals, filters, month-by-month, top-N, a join across files, an average.

| Model | Correct | Time per question |
| --- | --- | --- |
| gpt-oss:20b | 24/24 | 3.0 s |
| qwen3:8b | 23/24 | 14.2 s |

Three runs of each question, on an Apple M5 Pro. Eight questions on two files is a small test;
it shows the approach works, not that it never fails. The SQL is always printed so you can check it.

## Develop

```bash
git clone https://github.com/joeljo2347-bit/sheetsense && cd sheetsense
pip install -e ".[dev]"
pytest                               # no model needed: tests use a stand-in
python3 scripts/make_examples.py     # rebuild the example files
python3 scripts/accuracy.py          # needs Ollama
```

```
src/sheetsense/
  tables.py   spreadsheets → clean SQLite tables, and the schema the model sees
  guard.py    what may run (one SELECT, read-only, time-limited) and slips worth catching
  ask.py      question → SQL → answer, sending failures back to the model
  model.py    the Ollama client and the instructions
  cli.py      describe / ask / sql
```

## Limits

- One query per question. Questions that need several steps ("compare this month to the average
  of the last three, then explain") work only when they fit in one SELECT.
- The example data is made up. Your sheets will have surprises; `describe` shows how they loaded.
- Up to 500 result rows are returned per question.

## License

MIT
