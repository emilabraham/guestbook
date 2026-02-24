#!/usr/bin/env python3
"""Guestbook API — sanitizes, rate-limits, prints, and stores messages."""

import hashlib
import json
import os  # needed for DAILY_LIMIT env var
import sqlite3
import unicodedata
import urllib.request
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from pydantic import BaseModel, field_validator
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address

# ---------------------------------------------------------------------------
# Config (override via environment / .env loaded by systemd EnvironmentFile)
# ---------------------------------------------------------------------------
PRINTER_URL = "http://127.0.0.1:8765/print"
DB_PATH = Path(__file__).parent / "guestbook.db"
MAX_LENGTH = 10_000
DAILY_GLOBAL_LIMIT = int(os.environ.get("DAILY_LIMIT", "30"))

# ---------------------------------------------------------------------------
# Database
# ---------------------------------------------------------------------------

def init_db():
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS messages (
                id            INTEGER PRIMARY KEY AUTOINCREMENT,
                message       TEXT    NOT NULL,
                submitted_at  TEXT    NOT NULL,
                ip_hash       TEXT    NOT NULL,
                gallery_approved INTEGER DEFAULT 0
            )
        """)

# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------

limiter = Limiter(key_func=get_remote_address)

@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    yield

app = FastAPI(lifespan=lifespan)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# ---------------------------------------------------------------------------
# Sanitization
# ---------------------------------------------------------------------------

def sanitize(text: str) -> str:
    """Strip control characters (0x00–0x1F incl. ESC/GS, 0x7F, Unicode Cc/Cf).
    Newlines are preserved. Everything else printable is kept."""
    result = []
    for char in text:
        if char == "\n":
            result.append(char)
            continue
        cp = ord(char)
        # ASCII control range (includes ESC=0x1B, GS=0x1D) and DEL
        if cp < 0x20 or cp == 0x7F:
            continue
        # Unicode control/format/surrogate/private-use categories
        if unicodedata.category(char).startswith("C"):
            continue
        result.append(char)
    return "".join(result)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def call_printer(message: str):
    payload = json.dumps({"message": message}).encode()
    req = urllib.request.Request(
        PRINTER_URL,
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=5) as resp:
        if resp.status != 200:
            raise RuntimeError(f"Printer returned {resp.status}")


# ---------------------------------------------------------------------------
# Request model
# ---------------------------------------------------------------------------

class SubmitRequest(BaseModel):
    message: str

    @field_validator("message")
    @classmethod
    def validate_message(cls, v):
        if len(v) > MAX_LENGTH:
            raise ValueError(f"Message exceeds {MAX_LENGTH} characters")
        return v

# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@app.post("/submit")
@limiter.limit("3/hour")
async def submit(request: Request, body: SubmitRequest):
    clean = sanitize(body.message).strip()
    if not clean:
        raise HTTPException(400, "Message contains no printable content")

    today = datetime.now(timezone.utc).date().isoformat()
    ip_hash = hashlib.sha256(get_remote_address(request).encode()).hexdigest()[:16]

    with sqlite3.connect(DB_PATH) as conn:
        count_today = conn.execute(
            "SELECT COUNT(*) FROM messages WHERE submitted_at >= ?", (today,)
        ).fetchone()[0]
        if count_today >= DAILY_GLOBAL_LIMIT:
            raise HTTPException(429, "Daily message limit reached. Try again tomorrow.")

        conn.execute(
            "INSERT INTO messages (message, submitted_at, ip_hash) VALUES (?, ?, ?)",
            (clean, datetime.now(timezone.utc).isoformat(), ip_hash),
        )

    try:
        call_printer(clean)
    except Exception as e:
        raise HTTPException(502, f"Printer unavailable: {e}")

    return {"status": "ok"}


@app.get("/gallery")
async def gallery():
    with sqlite3.connect(DB_PATH) as conn:
        rows = conn.execute(
            "SELECT id, message, submitted_at FROM messages "
            "WHERE gallery_approved = 1 ORDER BY submitted_at DESC"
        ).fetchall()
    return [{"id": r[0], "message": r[1], "submitted_at": r[2]} for r in rows]


