"""
Pydantic models that enforce the JSON contract between the extraction pipeline
and Claude. Schema drift is caught at the boundary instead of leaking into the
database.
"""

import logging
from typing import Dict, Literal, Set

from pydantic import BaseModel, ConfigDict, Field

logger = logging.getLogger(__name__)


class DealStructure(BaseModel):
    """
    Strict schema for the output of the deal_analysis Claude prompt.

    `extra="forbid"` means any unexpected key from Claude raises ValidationError —
    schema drift in the high-level deal classification is a hard failure that
    we want to surface, not absorb.
    """

    model_config = ConfigDict(extra="forbid")

    deal_type: Literal[
        "Asset Purchase",
        "Stock Purchase",
        "Real Estate Purchase",
        "Construction",
        "Equipment",
        "Working Capital",
        "Refinance",
        "Other",
    ]
    has_real_estate: bool
    has_construction: bool
    has_equipment: bool
    has_seller: bool
    has_landlord_lease: bool
    borrower_count: int = Field(ge=1, le=10)
    has_second_borrower: bool
    has_personal_guarantors: bool
    personal_guarantor_count: int = Field(ge=0, le=20)
    has_corporate_guarantors: bool
    corporate_guarantor_count: int = Field(ge=0, le=20)
    loan_program: Literal[
        "SBA 7(a) Standard",
        "SBA 7(a) Express",
        "SBA 504",
        "Conventional",
    ]


class ExtractedFields(BaseModel):
    """
    Loose container for the dynamic field-extraction output.

    Keys depend on `build_schema(deal)`, so we cannot enumerate them here.
    Use `validate_extracted_fields()` below to gate the output through a single
    validation point that drops unexpected keys, coerces non-strings, and
    backfills missing expected keys with empty strings.
    """

    model_config = ConfigDict(extra="allow")


def validate_extracted_fields(
    raw: dict,
    expected_keys: Set[str],
) -> Dict[str, str]:
    """
    Reconcile a raw Claude field-extraction dict against the dynamic schema.

    Behavior:
    1. Unknown keys (not in `expected_keys`) are dropped with a warning log.
       Schema drift in fields is recoverable — we don't crash the pipeline.
    2. Non-string values are coerced via `str(v)` with a warning log.
    3. Missing expected keys are filled with `""`.

    Returns the cleaned dict whose key set is exactly `expected_keys`.
    """
    if not isinstance(raw, dict):
        raise TypeError(
            f"validate_extracted_fields expected a dict, got {type(raw).__name__}"
        )

    cleaned: Dict[str, str] = {}
    extras: list[str] = []
    coerced: list[str] = []

    for k, v in raw.items():
        if k not in expected_keys:
            extras.append(k)
            continue
        if v is None:
            cleaned[k] = ""
        elif isinstance(v, str):
            cleaned[k] = v
        else:
            coerced.append(k)
            cleaned[k] = str(v)

    if extras:
        logger.warning(
            "validate_extracted_fields: dropped %d unexpected key(s) from Claude: %s",
            len(extras), sorted(extras)[:20],
        )
    if coerced:
        logger.warning(
            "validate_extracted_fields: coerced %d non-string value(s) to str: %s",
            len(coerced), sorted(coerced)[:20],
        )

    for k in expected_keys:
        cleaned.setdefault(k, "")

    return cleaned
