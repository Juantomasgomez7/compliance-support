"""Database access for refunds.

All queries use bound parameters (never string-interpolated user input), so this
file is a clean contrast to an injectable query. Assumes a dict-row cursor
(e.g. psycopg2 ``RealDictCursor``).
"""
from __future__ import annotations


def get_refund(cursor, refund_id: str) -> dict | None:
    """Fetch a refund by id using a bound parameter."""
    cursor.execute("SELECT id, amount, status FROM refunds WHERE id = %s", (refund_id,))
    return cursor.fetchone()


def insert_refund(cursor, refund_id: str, amount_cents: int) -> None:
    """Insert a new refund row using bound parameters."""
    cursor.execute(
        "INSERT INTO refunds (id, amount, status) VALUES (%s, %s, %s)",
        (refund_id, amount_cents, "pending"),
    )
