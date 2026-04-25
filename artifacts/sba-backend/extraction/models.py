"""
Pydantic models that enforce the JSON contract between the extraction pipeline
and Claude. Schema drift is caught at the boundary instead of leaking into the
database.
"""

import logging
from typing import Dict, Literal, Set, Tuple

from pydantic import BaseModel, ConfigDict, Field

logger = logging.getLogger(__name__)

# Defensive cap for source-quote length — prompt asks for ≤25 words (~150 chars)
# but we don't trust the model. Anything longer is truncated with a "…" suffix.
_MAX_SOURCE_QUOTE_CHARS = 200

# Per-field allowed value sets. Fields not in this dict accept any string.
# Add entries here as the schema gains constrained-value fields. Empty for
# now — `LoanType` does NOT belong here because it's no longer extracted by
# the field-extraction prompt; the deal-analysis stage's DealStructure model
# already enforces `loan_program` via Literal[...] on the Pydantic side, and
# the pipeline mirrors that value into raw_data["LoanType"]. The point of
# keeping the dict (even empty) is so the validator infrastructure exists
# the moment a future constrained-value field is added.
ALLOWED_FIELD_VALUES: Dict[str, Set[str]] = {}


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
) -> Tuple[Dict[str, str], Dict[str, str]]:
    """
    Reconcile a raw Claude field-extraction dict against the dynamic schema.

    The v2 field_extraction prompt asks the model to return BOTH `<key>` and
    `<key>_source` for every schema key. This validator splits them into two
    parallel dicts.

    Behavior:
    1. Allowed keys are `expected_keys ∪ {f"{k}_source" for k in expected_keys}`.
       Anything else is dropped with a warning log (recoverable schema drift).
    2. Non-string values (in either values or sources) are coerced via `str(v)`
       with a warning log. `None` becomes `""`.
    3. Missing expected keys are filled with `""` in BOTH dicts.
    4. Source quotes longer than 200 chars are truncated to 200 chars with a
       trailing "…" and a warning log entry — defensive: the prompt asks for
       ≤25 words but we don't trust it.

    Returns:
        (values, sources)
        - values:  Dict[str, str], key set exactly `expected_keys`
        - sources: Dict[str, str], key set exactly `expected_keys`
    """
    if not isinstance(raw, dict):
        raise TypeError(
            f"validate_extracted_fields expected a dict, got {type(raw).__name__}"
        )

    source_keys: Set[str] = {f"{k}_source" for k in expected_keys}
    allowed: Set[str] = expected_keys | source_keys

    values: Dict[str, str] = {}
    sources: Dict[str, str] = {}
    extras: list[str] = []
    coerced_values: list[str] = []
    coerced_sources: list[str] = []
    truncated_sources: list[str] = []

    for k, v in raw.items():
        if k not in allowed:
            extras.append(k)
            continue

        # Normalize value: None -> "", non-string -> str(v) with warn
        if v is None:
            sv = ""
        elif isinstance(v, str):
            sv = v
        else:
            sv = str(v)
            (coerced_sources if k.endswith("_source") else coerced_values).append(k)

        if k.endswith("_source"):
            base = k[: -len("_source")]
            # Strip whitespace first — a whitespace-only quote carries no
            # evidence and would render as a confusing blank "Source:" line
            # in the UI. Treat it as "no quote".
            sv = sv.strip()
            if len(sv) > _MAX_SOURCE_QUOTE_CHARS:
                truncated_sources.append(base)
                # The trailing "…" is a sentinel the pipeline's quote
                # verifier knows to strip before substring-matching against
                # the source document. See `_verify_quote_in_source`.
                sv = sv[: _MAX_SOURCE_QUOTE_CHARS - 1].rstrip() + "…"
            sources[base] = sv
        else:
            values[k] = sv

    if extras:
        logger.warning(
            "validate_extracted_fields: dropped %d unexpected key(s) from Claude: %s",
            len(extras), sorted(extras)[:20],
        )
    if coerced_values:
        logger.warning(
            "validate_extracted_fields: coerced %d non-string value(s) to str: %s",
            len(coerced_values), sorted(coerced_values)[:20],
        )
    if coerced_sources:
        logger.warning(
            "validate_extracted_fields: coerced %d non-string source(s) to str: %s",
            len(coerced_sources), sorted(coerced_sources)[:20],
        )
    if truncated_sources:
        logger.warning(
            "validate_extracted_fields: truncated %d oversize source quote(s) to %d chars: %s",
            len(truncated_sources), _MAX_SOURCE_QUOTE_CHARS,
            sorted(truncated_sources)[:20],
        )

    for k in expected_keys:
        values.setdefault(k, "")
        sources.setdefault(k, "")

    # Final pass: enforce per-field allowed-value constraints. Any value
    # outside the declared set surfaces as a hard validation failure, which
    # the caller in schemas.extract_fields wraps as ExtractionStageError
    # with reason="schema_validation" — i.e. it appears in the existing
    # degraded-extraction UX rather than silently passing through.
    violations: list[str] = []
    for k, v in values.items():
        if not v:
            continue
        allowed = ALLOWED_FIELD_VALUES.get(k)
        if allowed is not None and v not in allowed:
            violations.append(f"{k}={v!r} (allowed: {sorted(allowed)})")

    if violations:
        logger.error(
            "validate_extracted_fields: %d field(s) violated allowed-value constraints: %s",
            len(violations), violations,
        )
        raise ValueError(
            f"Field-extraction output contained values outside allowed sets: {violations}"
        )

    return values, sources
