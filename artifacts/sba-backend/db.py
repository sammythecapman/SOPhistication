"""
Database layer for SBA extraction results.
Uses PostgreSQL via psycopg2 with the DATABASE_URL from environment.
"""

import os
import json
import psycopg2
import psycopg2.extras
from typing import Optional, List, Dict, Any
from contextlib import contextmanager


def get_connection():
    """Get a PostgreSQL connection."""
    db_url = os.environ.get("DATABASE_URL")
    if not db_url:
        raise RuntimeError("DATABASE_URL environment variable is not set")
    return psycopg2.connect(db_url, cursor_factory=psycopg2.extras.RealDictCursor)


@contextmanager
def get_cursor():
    """Context manager that provides a database cursor and auto-commits."""
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            yield cur
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_db():
    """Create tables if they don't exist."""
    with get_cursor() as cur:
        cur.execute("""
            CREATE TABLE IF NOT EXISTS sba_extractions (
                id SERIAL PRIMARY KEY,
                terms_filename TEXT NOT NULL,
                credit_memo_filename TEXT,
                deal_structure JSONB,
                raw_data JSONB,
                formatted_data JSONB NOT NULL DEFAULT '{}',
                ner_warnings JSONB NOT NULL DEFAULT '[]',
                fields_populated INTEGER NOT NULL DEFAULT 0,
                fields_total INTEGER NOT NULL DEFAULT 0,
                completion_pct NUMERIC(5,2) NOT NULL DEFAULT 0,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
        """)
        cur.execute("""
            CREATE INDEX IF NOT EXISTS idx_sba_extractions_created_at
            ON sba_extractions (created_at DESC)
        """)


def save_extraction(result: Dict[str, Any]) -> int:
    """Save an extraction result and return the new row ID."""
    summary = result.get("summary", {})
    with get_cursor() as cur:
        cur.execute("""
            INSERT INTO sba_extractions
                (terms_filename, credit_memo_filename, deal_structure, raw_data,
                 formatted_data, ner_warnings, fields_populated, fields_total, completion_pct)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING id
        """, (
            result.get("terms_filename", ""),
            result.get("credit_memo_filename"),
            json.dumps(result.get("deal_structure") or {}),
            json.dumps(result.get("raw_data") or {}),
            json.dumps(result.get("formatted_data") or {}),
            json.dumps(result.get("ner_warnings") or []),
            summary.get("fields_populated", 0),
            summary.get("fields_total", 0),
            summary.get("completion_percentage", 0),
        ))
        row = cur.fetchone()
        return row["id"]


def get_extraction(extraction_id: int) -> Optional[Dict[str, Any]]:
    """Get a single extraction by ID."""
    with get_cursor() as cur:
        cur.execute(
            "SELECT * FROM sba_extractions WHERE id = %s",
            (extraction_id,)
        )
        row = cur.fetchone()
        if not row:
            return None
        return _row_to_dict(row)


def list_extractions(page: int = 1, per_page: int = 20) -> Dict[str, Any]:
    """List extractions with pagination."""
    offset = (page - 1) * per_page
    with get_cursor() as cur:
        cur.execute("SELECT COUNT(*) as total FROM sba_extractions")
        total = cur.fetchone()["total"]

        cur.execute("""
            SELECT id, terms_filename, credit_memo_filename, deal_structure,
                   formatted_data, ner_warnings, fields_populated, fields_total,
                   completion_pct, created_at
            FROM sba_extractions
            ORDER BY created_at DESC
            LIMIT %s OFFSET %s
        """, (per_page, offset))

        rows = cur.fetchall()
        extractions = [_row_to_summary(row) for row in rows]

    total_pages = max(1, (total + per_page - 1) // per_page)
    return {
        "extractions": extractions,
        "total": total,
        "page": page,
        "per_page": per_page,
        "total_pages": total_pages,
    }


def delete_extraction(extraction_id: int) -> bool:
    """Delete an extraction by ID. Returns True if deleted."""
    with get_cursor() as cur:
        cur.execute(
            "DELETE FROM sba_extractions WHERE id = %s RETURNING id",
            (extraction_id,)
        )
        return cur.fetchone() is not None


def _row_to_summary(row) -> Dict[str, Any]:
    """Convert a DB row to the summary format for the list endpoint."""
    row = dict(row)
    formatted = row.get("formatted_data") or {}
    deal = row.get("deal_structure") or {}
    ner_warnings = row.get("ner_warnings") or []

    return {
        "id": row["id"],
        "terms_filename": row["terms_filename"],
        "credit_memo_filename": row.get("credit_memo_filename"),
        "deal_type": deal.get("deal_type"),
        "loan_program": deal.get("loan_program"),
        "borrower_name": formatted.get("Borrower1Name") or None,
        "loan_amount": formatted.get("LoanAmountShort") or None,
        "fields_populated": row["fields_populated"],
        "fields_total": row["fields_total"],
        "completion_pct": float(row["completion_pct"]),
        "created_at": row["created_at"].isoformat() if row.get("created_at") else "",
        "has_ner_warnings": len(ner_warnings) > 0,
    }


def _row_to_dict(row) -> Dict[str, Any]:
    """Convert a DB row to the full detail format."""
    row = dict(row)
    ner_warnings = row.get("ner_warnings") or []

    return {
        "id": row["id"],
        "terms_filename": row["terms_filename"],
        "credit_memo_filename": row.get("credit_memo_filename"),
        "deal_structure": row.get("deal_structure") or {},
        "formatted_data": row.get("formatted_data") or {},
        "raw_data": row.get("raw_data") or {},
        "ner_warnings": ner_warnings if isinstance(ner_warnings, list) else [],
        "fields_populated": row["fields_populated"],
        "fields_total": row["fields_total"],
        "completion_pct": float(row["completion_pct"]),
        "created_at": row["created_at"].isoformat() if row.get("created_at") else "",
    }
