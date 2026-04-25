"""
Backfill formatted_data.LoanType in existing extractions to mirror
deal_structure.loan_program. Run once after deploying the LoanType fix.

Idempotent: safe to re-run. Updates only rows where the current LoanType
differs from deal_structure.loan_program.
"""

import os
import sys
import json
from pathlib import Path

THIS_DIR = Path(__file__).resolve().parent
BACKEND_DIR = THIS_DIR.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

import db  # noqa: E402


def backfill() -> int:
    if not os.environ.get("DATABASE_URL"):
        raise RuntimeError("DATABASE_URL is not set; cannot run backfill.")

    updated = 0
    with db.get_cursor() as cur:
        cur.execute("""
            SELECT id, deal_structure, formatted_data, raw_data, field_sources
            FROM sba_extractions
        """)
        rows = cur.fetchall()

        for row in rows:
            deal = row["deal_structure"] or {}
            formatted = row["formatted_data"] or {}
            raw = row["raw_data"] or {}
            sources = row["field_sources"] or {}

            program = (deal.get("loan_program") or "").strip()
            if not program:
                continue
            current = (formatted.get("LoanType") or "").strip()
            if current == program:
                continue

            formatted["LoanType"] = program
            raw["LoanType"] = program
            sources["LoanType"] = {"quote": "[deal_analysis]", "verified": None}

            cur.execute("""
                UPDATE sba_extractions
                SET formatted_data = %s,
                    raw_data       = %s,
                    field_sources  = %s
                WHERE id = %s
            """, (
                json.dumps(formatted),
                json.dumps(raw),
                json.dumps(sources),
                row["id"],
            ))
            updated += 1

    return updated


if __name__ == "__main__":
    n = backfill()
    if n == 0:
        print("Backfill complete: all rows already aligned.")
    else:
        print(f"Backfill complete: corrected LoanType on {n} row(s).")
