"""Lender registry loaded from lenders.csv.

Resolves LOOKUP-type fields (LenderDescription, LenderAddress*,
LenderSigner*) without invoking Claude. The CSV may be absent — in
that case the registry loads cleanly, logs one warning, and every
lookup returns None until the file is added.
"""

import csv
import logging
import re
from pathlib import Path
from typing import Dict, List, Optional

from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

CSV_PATH = Path(__file__).parent / "lenders.csv"

_WS_RE = re.compile(r"\s+")


def _normalize(s: str) -> str:
    """Lowercase + collapse internal whitespace + strip. Used as the key
    for case- and whitespace-insensitive lookup. The original string is
    never modified — only the lookup key derived from it.
    """
    if not s:
        return ""
    return _WS_RE.sub(" ", s).strip().lower()


class LenderRecord(BaseModel):
    lender_name: str
    lender_description: str = ""
    lender_address_1: str = ""
    lender_address_2: str = ""
    lender_signer_name: str = ""
    lender_signer_title: str = ""
    aliases: List[str] = Field(default_factory=list)


class LenderRegistry:
    """Module-level singleton. Loaded once at import time."""

    _records: List[LenderRecord] = []
    _by_key: Dict[str, LenderRecord] = {}
    _missing: bool = False

    @classmethod
    def _load(cls, path: Path = CSV_PATH) -> None:
        cls._records = []
        cls._by_key = {}
        cls._missing = False
        if not path.exists():
            cls._missing = True
            logger.warning(
                "lenders.csv not found at %s; LOOKUP fields will resolve to "
                "None until the file is added", path,
            )
            return
        with open(path, "r", encoding="utf-8-sig", newline="") as fh:
            reader = csv.DictReader(fh)
            for raw in reader:
                row = {
                    k: (v.strip() if isinstance(v, str) else v)
                    for k, v in raw.items()
                }
                aliases = [
                    a.strip() for a in (row.get("aliases", "") or "").split("|")
                    if a.strip()
                ]
                rec = LenderRecord(
                    lender_name=row["lender_name"],
                    lender_description=row.get("lender_description", "") or "",
                    lender_address_1=row.get("lender_address_1", "") or "",
                    lender_address_2=row.get("lender_address_2", "") or "",
                    lender_signer_name=row.get("lender_signer_name", "") or "",
                    lender_signer_title=row.get("lender_signer_title", "") or "",
                    aliases=aliases,
                )
                cls._records.append(rec)
                # Canonical-name key wins over alias key on collision.
                cls._by_key[_normalize(rec.lender_name)] = rec
                for a in aliases:
                    cls._by_key.setdefault(_normalize(a), rec)
        logger.info(
            "LenderRegistry loaded %d lender record(s) from %s",
            len(cls._records), path,
        )

    @classmethod
    def lookup(cls, lender_name: str) -> Optional[LenderRecord]:
        if not lender_name:
            return None
        return cls._by_key.get(_normalize(lender_name))

    @classmethod
    def all_lenders(cls) -> List[LenderRecord]:
        return list(cls._records)

    @classmethod
    def canonical_names(cls) -> List[str]:
        return [r.lender_name for r in cls._records]


LenderRegistry._load()
