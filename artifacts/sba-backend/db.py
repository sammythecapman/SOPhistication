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
                confidence_scores JSONB NOT NULL DEFAULT '{}',
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
        # Add confidence_scores column to existing tables that predate it
        cur.execute("""
            ALTER TABLE sba_extractions
            ADD COLUMN IF NOT EXISTS confidence_scores JSONB NOT NULL DEFAULT '{}'
        """)
        # Add extraction_health column for surfacing degraded pipeline runs
        cur.execute("""
            ALTER TABLE sba_extractions
            ADD COLUMN IF NOT EXISTS extraction_health JSONB
        """)
        # Per-extraction prompt version tags so we can audit which prompt
        # produced each row when iterating on prompt text.
        cur.execute("""
            ALTER TABLE sba_extractions
            ADD COLUMN IF NOT EXISTS deal_analysis_prompt_version TEXT
        """)
        cur.execute("""
            ALTER TABLE sba_extractions
            ADD COLUMN IF NOT EXISTS field_extraction_prompt_version TEXT
        """)

        # ── File access audit log ──
        cur.execute("""
            CREATE TABLE IF NOT EXISTS file_access_log (
                id SERIAL PRIMARY KEY,
                extraction_id INTEGER,
                filename TEXT NOT NULL,
                action TEXT NOT NULL,
                ip_address TEXT,
                success BOOLEAN NOT NULL DEFAULT TRUE,
                error_reason TEXT,
                accessed_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
        """)
        cur.execute("""
            CREATE INDEX IF NOT EXISTS idx_file_access_log_extraction
            ON file_access_log (extraction_id, accessed_at DESC)
        """)

        # ── Feedback table ──
        cur.execute("""
            CREATE TABLE IF NOT EXISTS validation_feedback (
                id SERIAL PRIMARY KEY,
                extraction_id INTEGER REFERENCES sba_extractions(id) ON DELETE CASCADE,
                field_name TEXT NOT NULL,
                extracted_value TEXT NOT NULL,
                confidence_tier TEXT NOT NULL,
                reviewer_verdict TEXT NOT NULL,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
        """)
        cur.execute("""
            CREATE INDEX IF NOT EXISTS idx_validation_feedback_field
            ON validation_feedback (field_name)
        """)
        cur.execute("""
            CREATE INDEX IF NOT EXISTS idx_validation_feedback_created
            ON validation_feedback (created_at DESC)
        """)


# ──────────────────────────────────────────────
# Extractions CRUD
# ──────────────────────────────────────────────

def save_extraction(result: Dict[str, Any]) -> int:
    """Save an extraction result and return the new row ID."""
    summary = result.get("summary", {})
    prompt_versions = result.get("prompt_versions") or {}
    with get_cursor() as cur:
        cur.execute("""
            INSERT INTO sba_extractions
                (terms_filename, credit_memo_filename, deal_structure, raw_data,
                 formatted_data, ner_warnings, confidence_scores, extraction_health,
                 deal_analysis_prompt_version, field_extraction_prompt_version,
                 fields_populated, fields_total, completion_pct)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING id
        """, (
            result.get("terms_filename", ""),
            result.get("credit_memo_filename"),
            json.dumps(result.get("deal_structure") or {}),
            json.dumps(result.get("raw_data") or {}),
            json.dumps(result.get("formatted_data") or {}),
            json.dumps(result.get("ner_warnings") or []),
            json.dumps(result.get("confidence_scores") or {}),
            json.dumps(result.get("extraction_health") or {"degraded": False, "stage_failures": []}),
            prompt_versions.get("deal_analysis"),
            prompt_versions.get("field_extraction"),
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


# ──────────────────────────────────────────────
# File access audit log
# ──────────────────────────────────────────────

def log_file_access(
    extraction_id: int,
    filename: str,
    action: str,
    ip_address: str,
    success: bool,
    error_reason: str = None,
) -> None:
    """Record a file access event to the audit log. Never raises."""
    try:
        with get_cursor() as cur:
            cur.execute("""
                INSERT INTO file_access_log
                    (extraction_id, filename, action, ip_address, success, error_reason)
                VALUES (%s, %s, %s, %s, %s, %s)
            """, (extraction_id, filename, action, ip_address, success, error_reason))
    except Exception as e:
        print(f"⚠️  Audit log write failed: {e}")


# ──────────────────────────────────────────────
# Feedback CRUD
# ──────────────────────────────────────────────

def save_feedback(
    extraction_id: int,
    field_name: str,
    extracted_value: str,
    confidence_tier: str,
    reviewer_verdict: str,
) -> int:
    """Record a reviewer verdict on a flagged field. Returns new feedback row ID."""
    with get_cursor() as cur:
        cur.execute("""
            INSERT INTO validation_feedback
                (extraction_id, field_name, extracted_value, confidence_tier, reviewer_verdict)
            VALUES (%s, %s, %s, %s, %s)
            RETURNING id
        """, (extraction_id, field_name, extracted_value, confidence_tier, reviewer_verdict))
        row = cur.fetchone()
        return row["id"]


def get_learned_suppressions() -> Dict[str, str]:
    """
    Compute current threshold adjustments from cumulative feedback.

    Returns: {field_name: "suppress_yellow" | "downgrade_red"}

    Rules:
    - Yellow flag FP rate > 90% over >= 20 reviews → suppress_yellow
    - Red flag FP rate > 80% over >= 10 reviews → downgrade_red
    """
    with get_cursor() as cur:
        cur.execute("""
            SELECT
                field_name,
                confidence_tier,
                COUNT(*) FILTER (WHERE reviewer_verdict = 'correct') AS correct_count,
                COUNT(*) AS total_count
            FROM validation_feedback
            GROUP BY field_name, confidence_tier
        """)
        rows = cur.fetchall()

    suppressions: Dict[str, str] = {}
    for row in rows:
        field = row["field_name"]
        tier = row["confidence_tier"]
        correct = row["correct_count"]
        total = row["total_count"]
        if total == 0:
            continue
        fp_rate = correct / total  # "correct" verdict = the flag was a false positive

        if tier == "yellow" and total >= 20 and fp_rate > 0.90:
            suppressions[field] = "suppress_yellow"
        elif tier == "red" and total >= 10 and fp_rate > 0.80:
            # Only downgrade if not already suppressed
            if field not in suppressions:
                suppressions[field] = "downgrade_red"

    return suppressions


def reset_field_learning(field_name: str) -> int:
    """Delete all feedback for a specific field. Returns count deleted."""
    with get_cursor() as cur:
        cur.execute(
            "DELETE FROM validation_feedback WHERE field_name = %s",
            (field_name,)
        )
        return cur.rowcount


# ──────────────────────────────────────────────
# Analytics
# ──────────────────────────────────────────────

def get_analytics() -> Dict[str, Any]:
    """Compile analytics data for the dashboard."""
    with get_cursor() as cur:
        # Total extractions
        cur.execute("SELECT COUNT(*) AS total FROM sba_extractions")
        total_extractions = cur.fetchone()["total"]

        # Flag counts from confidence_scores stored per extraction
        cur.execute("""
            SELECT
                COUNT(*) FILTER (WHERE reviewer_verdict = 'correct') AS false_positives,
                COUNT(*) FILTER (WHERE reviewer_verdict = 'incorrect') AS true_positives,
                COUNT(*) AS total
            FROM validation_feedback
        """)
        verdict_row = cur.fetchone()

        cur.execute("""
            SELECT
                COUNT(*) FILTER (WHERE confidence_tier = 'red') AS red_count,
                COUNT(*) FILTER (WHERE confidence_tier = 'yellow') AS yellow_count
            FROM validation_feedback
        """)
        tier_row = cur.fetchone()

        # Per-field stats
        cur.execute("""
            SELECT
                field_name,
                confidence_tier,
                COUNT(*) FILTER (WHERE reviewer_verdict = 'correct') AS correct_count,
                COUNT(*) FILTER (WHERE reviewer_verdict = 'incorrect') AS incorrect_count,
                COUNT(*) AS total_count
            FROM validation_feedback
            GROUP BY field_name, confidence_tier
            ORDER BY field_name, confidence_tier
        """)
        field_rows = cur.fetchall()

        # Recent feedback (last 50)
        cur.execute("""
            SELECT vf.id, vf.extraction_id, vf.field_name, vf.extracted_value,
                   vf.confidence_tier, vf.reviewer_verdict, vf.created_at
            FROM validation_feedback vf
            ORDER BY vf.created_at DESC
            LIMIT 50
        """)
        recent_rows = cur.fetchall()

    # Build per-field stats
    field_stats: Dict[str, Dict] = {}
    for row in field_rows:
        fn = row["field_name"]
        tier = row["confidence_tier"]
        if fn not in field_stats:
            field_stats[fn] = {"field_name": fn, "yellow": {}, "red": {}}
        total = row["total_count"]
        correct = row["correct_count"]
        fp_rate = round(correct / total, 3) if total else 0.0
        field_stats[fn][tier] = {
            "total": total,
            "correct": correct,
            "incorrect": row["incorrect_count"],
            "false_positive_rate": fp_rate,
        }

    suppressions = get_learned_suppressions()
    for fn, stats in field_stats.items():
        stats["auto_suppression"] = suppressions.get(fn)

    recent_feedback = [
        {
            "id": r["id"],
            "extraction_id": r["extraction_id"],
            "field_name": r["field_name"],
            "extracted_value": r["extracted_value"],
            "confidence_tier": r["confidence_tier"],
            "reviewer_verdict": r["reviewer_verdict"],
            "created_at": r["created_at"].isoformat() if r.get("created_at") else "",
        }
        for r in recent_rows
    ]

    return {
        "total_extractions": total_extractions,
        "total_flags": {
            "red": tier_row["red_count"] if tier_row else 0,
            "yellow": tier_row["yellow_count"] if tier_row else 0,
        },
        "total_reviewed": {
            "total": verdict_row["total"] if verdict_row else 0,
            "false_positives": verdict_row["false_positives"] if verdict_row else 0,
            "true_positives": verdict_row["true_positives"] if verdict_row else 0,
        },
        "field_stats": list(field_stats.values()),
        "auto_suppressions": suppressions,
        "recent_feedback": recent_feedback,
    }


# ──────────────────────────────────────────────
# Row helpers
# ──────────────────────────────────────────────

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

    deal_pv = row.get("deal_analysis_prompt_version")
    field_pv = row.get("field_extraction_prompt_version")
    prompt_versions: Optional[Dict[str, str]] = None
    if deal_pv or field_pv:
        prompt_versions = {
            "deal_analysis": deal_pv,
            "field_extraction": field_pv,
        }

    return {
        "id": row["id"],
        "terms_filename": row["terms_filename"],
        "credit_memo_filename": row.get("credit_memo_filename"),
        "deal_structure": row.get("deal_structure") or {},
        "formatted_data": row.get("formatted_data") or {},
        "raw_data": row.get("raw_data") or {},
        "ner_warnings": ner_warnings if isinstance(ner_warnings, list) else [],
        "confidence_scores": row.get("confidence_scores") or {},
        "extraction_health": row.get("extraction_health") or {"degraded": False, "stage_failures": []},
        "prompt_versions": prompt_versions,
        "fields_populated": row["fields_populated"],
        "fields_total": row["fields_total"],
        "completion_pct": float(row["completion_pct"]),
        "created_at": row["created_at"].isoformat() if row.get("created_at") else "",
    }
