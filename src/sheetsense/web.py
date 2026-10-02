"""The web demo: pick the example spreadsheets or upload your own, ask a question, see the answer and its SQL.

    pip install -e ".[web]"
    uvicorn sheetsense.web:app --port 8000

Built to sit on the public internet: uploads are size-checked and read in memory, one question
runs on the model at a time, and each visitor gets a limited number of questions.
"""

from __future__ import annotations

import asyncio
import io
import os
import tempfile
import time
import zipfile
from collections import defaultdict, deque
from functools import lru_cache
from pathlib import Path
from typing import Deque, Dict, List, Optional

from fastapi import FastAPI, File, Form, Request, UploadFile
from fastapi.responses import FileResponse, JSONResponse

from . import guard
from .ask import CouldNotAnswer, ask
from .model import DEFAULT_MODEL, Ollama
from .tables import Table, describe, load, open_db

HERE = Path(__file__).resolve().parent
EXAMPLES = Path(os.environ.get("SHEETSENSE_EXAMPLES", HERE.parent.parent / "examples"))
MAX_FILES, MAX_BYTES, MAX_UNZIPPED = 3, 2_000_000, 40_000_000
MAX_QUESTION = 300
PER_VISITOR, WINDOW = int(os.environ.get("SHEETSENSE_RATE", "15")), 600  # questions per 10 minutes
MAX_WAITING = 6
SHOWN_ROWS = 200

EXAMPLE_FILES = {
    "sales_2025.xlsx": "Orders 2025 for Lumen Supply Co., a made-up office-supply company: 289 orders, a title row, money typed as text, a Total row.",
    "webinar_attendance.csv": "Who signed up for the company's webinars, and whether they came.",
}
SUGGESTIONS = [
    "How much is unpaid, by rep?",
    "Which region sold the most in Q3, and how much?",
    "Total sales month by month.",
    "Which customers attended a webinar but never placed an order?",
    "What are the top 3 products by revenue?",
]

app = FastAPI(title="sheetsense", docs_url=None, redoc_url=None, openapi_url=None)
model = Ollama(os.environ.get("SHEETSENSE_MODEL", DEFAULT_MODEL), timeout=180)
turn = asyncio.Lock()
waiting = 0
asked: Dict[str, Deque[float]] = defaultdict(deque)


def visitor(request: Request) -> str:
    """The visitor's address. Behind the local proxy, the one it forwards."""
    peer = request.client.host if request.client else "?"
    forwarded = request.headers.get("x-forwarded-for")
    return forwarded.split(",")[0].strip() if forwarded and peer in ("127.0.0.1", "::1") else peer


def over_limit(who: str) -> Optional[int]:
    """Seconds until this visitor may ask again, or None."""
    now = time.monotonic()
    times = asked[who]
    while times and now - times[0] > WINDOW:
        times.popleft()
    if len(times) >= PER_VISITOR:
        return int(WINDOW - (now - times[0])) + 1
    times.append(now)
    return None


def fail(status: int, message: str, **extra) -> JSONResponse:
    return JSONResponse({"error": message, **extra}, status_code=status)


def check_upload(name: str, data: bytes) -> Optional[str]:
    suffix = Path(name).suffix.lower()
    if suffix not in (".xlsx", ".csv"):
        return f"{name}: only .xlsx and .csv files can be read."
    if len(data) > MAX_BYTES:
        return f"{name} is over 2 MB; try a smaller export."
    if suffix == ".xlsx":
        try:
            with zipfile.ZipFile(io.BytesIO(data)) as z:
                if sum(i.file_size for i in z.infolist()) > MAX_UNZIPPED or len(z.infolist()) > 500:
                    return f"{name} is too large once unpacked."
        except zipfile.BadZipFile:
            return f"{name} isn't a valid .xlsx file."
    return None


def summary(tables: List[Table]) -> List[dict]:
    return [{"name": t.name, "source": t.source, "rows": t.rows, "columns": [c.heading for c in t.columns]} for t in tables]


@app.get("/")
def page() -> FileResponse:
    return FileResponse(HERE / "static" / "index.html", headers={"Cache-Control": "no-cache"})


@app.get("/healthz")
def healthz() -> dict:
    return {"ok": True}


@app.get("/api/examples")
@lru_cache(maxsize=1)
def examples() -> dict:
    db = open_db()
    tables = load(db, [EXAMPLES / name for name in EXAMPLE_FILES])
    return {
        "files": [{"name": n, "about": a} for n, a in EXAMPLE_FILES.items()],
        "tables": summary(tables),
        "suggestions": SUGGESTIONS,
        "model": model.model,
    }


@app.get("/examples/{name}")
def download_example(name: str):
    if name not in EXAMPLE_FILES:
        return fail(404, "No such example.")
    return FileResponse(EXAMPLES / name, filename=name)


@app.post("/api/ask")
async def api_ask(
    request: Request,
    question: str = Form(...),
    examples: str = Form(""),
    files: List[UploadFile] = File(default=[]),
):
    global waiting
    question = question.strip()
    if not question:
        return fail(400, "Type a question first.")
    if len(question) > MAX_QUESTION:
        return fail(400, f"Keep the question under {MAX_QUESTION} characters.")
    files = [f for f in files if f.filename]
    chosen = [n for n in examples.split(",") if n in EXAMPLE_FILES]
    if not files and not chosen:
        return fail(400, "Pick an example file or upload a spreadsheet.")
    if len(files) > MAX_FILES:
        return fail(400, f"Up to {MAX_FILES} files at a time.")
    wait = over_limit(visitor(request))
    if wait:
        return fail(429, f"That's the limit for now. Try again in about {max(1, wait // 60)} minute(s).")
    if waiting >= MAX_WAITING:
        return fail(503, "The demo is busy answering other people. Try again in a minute.")

    with tempfile.TemporaryDirectory(prefix="sheetsense-") as tmp:
        paths = [EXAMPLES / n for n in chosen]
        for f in files:
            data = await f.read(MAX_BYTES + 1)
            problem = check_upload(f.filename, data)
            if problem:
                return fail(400, problem)
            path = Path(tmp) / Path(f.filename).name
            path.write_bytes(data)
            paths.append(path)
        db = open_db()
        try:
            tables = load(db, paths)
        except Exception:  # a broken or unusual file: say so rather than fail the page
            return fail(400, "Couldn't read that file. Is it a normal .xlsx or .csv export?")
        if not tables:
            return fail(400, "No sheet has a row of headings over its data.")

        waiting += 1
        started = time.monotonic()
        try:
            async with turn:  # one question on the model at a time: it's a single CPU-bound model
                loop = asyncio.get_running_loop()
                answer = await loop.run_in_executor(None, ask, question, db, tables, model)
        except CouldNotAnswer as e:
            return fail(422, "The model couldn't write a working query for that. Try rephrasing it.", attempts=e.attempts)
        except ConnectionError:
            return fail(503, "The model isn't available right now. Try again in a minute.")
        finally:
            waiting -= 1
            db.close()

    result: guard.Result = answer.result
    return {
        "sql": answer.sql,
        "note": answer.note,
        "columns": result.columns,
        "rows": [list(r) for r in result.rows[:SHOWN_ROWS]],
        "total_rows": len(result.rows),
        "cut": result.cut or len(result.rows) > SHOWN_ROWS,
        "retries": len(answer.attempts),
        "seconds": round(time.monotonic() - started, 1),
        "tables": summary(tables),
        "schema": describe(tables),
    }
