"""
Marks all pre-existing extractions as having been produced by an unversioned
prompt. Run once after deploying the prompt-versioning change.

Idempotent: only updates rows where deal_analysis_prompt_version IS NULL.
Re-running is safe and a no-op once every legacy row is tagged.

Usage:
    python -m scripts.backfill_prompt_versions
or, from the backend dir:
    python scripts/backfill_prompt_versions.py
"""

import os
import sys
from pathlib import Path

# Allow running this script directly from the artifacts/sba-backend directory.
THIS_DIR = Path(__file__).resolve().parent
BACKEND_DIR = THIS_DIR.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

import db  # noqa: E402  (import after sys.path adjustment)


PRE_VERSIONING_TAG = "pre-versioning"


def backfill() -> int:
    """Tag every untagged extraction row as pre-versioning. Returns row count updated."""
    if not os.environ.get("DATABASE_URL"):
        raise RuntimeError("DATABASE_URL is not set; cannot run backfill.")

    with db.get_cursor() as cur:
        cur.execute(
            """
            UPDATE sba_extractions
               SET deal_analysis_prompt_version    = %s,
                   field_extraction_prompt_version = %s
             WHERE deal_analysis_prompt_version IS NULL
            """,
            (PRE_VERSIONING_TAG, PRE_VERSIONING_TAG),
        )
        return cur.rowcount


if __name__ == "__main__":
    n = backfill()
    if n == 0:
        print("Backfill complete: no untagged rows found (already idempotent).")
    else:
        print(f"Backfill complete: tagged {n} row(s) as '{PRE_VERSIONING_TAG}'.")
