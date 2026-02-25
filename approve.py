#!/usr/bin/env python3
"""CLI moderation tool — approve guestbook messages for the gallery."""

import sqlite3
import sys
import textwrap
from pathlib import Path

DB_PATH = Path(__file__).parent / "guestbook.db"


def first_line(message: str, width: int = 60) -> str:
    line = message.split("\n")[0]
    return line[:width] + "..." if len(line) > width else line


def list_pending(conn):
    rows = conn.execute(
        "SELECT id, submitted_at, message FROM messages "
        "WHERE gallery_approved = 0 ORDER BY submitted_at ASC"
    ).fetchall()
    if not rows:
        print("No pending messages.")
        return []
    print(f"\n{'ID':>4}  {'Date':>10}  First line")
    print("-" * 72)
    for r in rows:
        print(f"{r[0]:>4}  {r[1][:10]}  {first_line(r[2])}")
    print()
    return rows


def approve_message(conn, message_id: int):
    row = conn.execute(
        "SELECT id, message FROM messages WHERE id = ? AND gallery_approved = 0",
        (message_id,),
    ).fetchone()
    if row is None:
        print(f"No pending message with ID {message_id}.")
        return

    print(f"\n--- Message {row[0]} ---")
    print(textwrap.indent(row[1], "  "))
    print("---")

    commentary = input("Commentary (leave blank for none): ").strip()
    confirm = input(f"Approve message {row[0]}? [y/N] ").strip().lower()
    if confirm != "y":
        print("Cancelled.")
        return

    conn.execute(
        "UPDATE messages SET gallery_approved = 1, commentary = ? WHERE id = ?",
        (commentary or None, row[0]),
    )
    conn.commit()
    print(f"Message {row[0]} approved.")


def main():
    with sqlite3.connect(DB_PATH) as conn:
        while True:
            list_pending(conn)
            try:
                raw = input("Enter ID to approve (or q to quit): ").strip()
            except (EOFError, KeyboardInterrupt):
                print()
                sys.exit(0)
            if raw.lower() in ("q", "quit", ""):
                break
            if not raw.isdigit():
                print("Please enter a numeric ID.")
                continue
            approve_message(conn, int(raw))


if __name__ == "__main__":
    main()
