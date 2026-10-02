"""Talking to a local model through Ollama. Nothing leaves the computer."""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from typing import List, Protocol

DEFAULT_MODEL = os.environ.get("SHEETSENSE_MODEL", "gpt-oss:20b")
def ollama_url(host: str) -> str:
    """OLLAMA_HOST as Ollama itself accepts it: "0.0.0.0:11434", "localhost" or a full URL."""
    host = host.strip().rstrip("/") or "127.0.0.1:11434"
    if "://" in host:
        return host  # a full URL is used as given
    host = host.replace("0.0.0.0", "127.0.0.1")
    return f"http://{host if ':' in host else host + ':11434'}"


OLLAMA_URL = ollama_url(os.environ.get("OLLAMA_HOST", ""))

SYSTEM = """You answer questions about spreadsheets by writing one SQLite SELECT.

The spreadsheets are loaded as tables. Their columns, types and some values are listed below.
Rules:
- Write exactly one SELECT (or WITH ... SELECT). Never change data.
- Let SQL do every count, sum, average and comparison. Never compute figures yourself.
- Number columns are already numbers: use them directly, no SUBSTR or CAST to strip "$".
- Dates are text "yyyy-mm-dd": use substr(date,1,7) for a month, strftime for more.
- Text matches ignore case. For "in one list but not the other", use NOT IN or LEFT JOIN ... IS NULL.
- Name result columns plainly (AS "Total sales").

Reply with JSON only: {"sql": "...", "note": "one short sentence on how the query answers the question"}"""


class Model(Protocol):
    def complete(self, messages: List[dict]) -> str: ...


class Ollama:
    def __init__(self, model: str = DEFAULT_MODEL, url: str = OLLAMA_URL, timeout: float = 300):
        self.model, self.url, self.timeout = model, url, timeout

    def complete(self, messages: List[dict]) -> str:
        body = {
            "model": self.model,
            "messages": messages,
            "stream": False,
            "format": "json",
            "options": {"temperature": 0.1},
        }
        req = urllib.request.Request(f"{self.url}/api/chat", data=json.dumps(body).encode(), headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as res:
                data = json.loads(res.read())
        except urllib.error.HTTPError as e:
            detail = e.read().decode(errors="replace")
            try:
                detail = json.loads(detail).get("error", detail)
            except (json.JSONDecodeError, AttributeError):
                pass
            raise ConnectionError(f"Ollama refused the request: {detail}") from e
        except urllib.error.URLError as e:
            raise ConnectionError(
                f"Couldn't reach Ollama at {self.url} ({e.reason}). Start it with `ollama serve` and pull a model: `ollama pull {self.model}`."
            ) from e
        except (OSError, ValueError) as e:  # a timeout while reading, or a reply that isn't JSON
            raise ConnectionError(f"Ollama didn't give a usable answer ({e}).") from e
        if "message" not in data:
            raise ConnectionError(f"Unexpected reply from Ollama: {str(data)[:200]}")
        return data["message"].get("content") or ""
