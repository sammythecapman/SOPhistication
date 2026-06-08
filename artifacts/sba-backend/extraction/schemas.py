"""
Deal structure analysis and dynamic schema building.

The actual prompt text lives in `extraction/prompts/<name>/vN.txt` and is
loaded via `prompts.registry.load_prompt`. This module is responsible only
for orchestrating the call, parsing/validating the response (Pydantic), and
returning the (data, prompt_version) tuple to the pipeline.
"""

import json
import time
import logging
import anthropic
from typing import Dict, Tuple

from pydantic import ValidationError

from .errors import ExtractionStageError
from .field_registry import FieldRegistry
from .models import DealStructure, validate_extracted_fields
from .prompts.registry import load_prompt

logger = logging.getLogger(__name__)


def _claude_with_retry(client, max_retries: int = 5, **kwargs):
    """
    Call client.messages.create with exponential backoff on overloaded (529) errors.
    Retries up to max_retries times with delays: 2s, 4s, 8s, 16s, 32s.
    """
    delay = 2
    for attempt in range(max_retries):
        try:
            return client.messages.create(**kwargs)
        except anthropic.APIStatusError as e:
            if e.status_code == 529 and attempt < max_retries - 1:
                logger.warning(
                    "Claude overloaded (attempt %d/%d), retrying in %ds...",
                    attempt + 1, max_retries, delay,
                )
                time.sleep(delay)
                delay = min(delay * 2, 60)
            else:
                raise
        except anthropic.APIConnectionError:
            if attempt < max_retries - 1:
                logger.warning(
                    "Claude connection error (attempt %d/%d), retrying in %ds...",
                    attempt + 1, max_retries, delay,
                )
                time.sleep(delay)
                delay = min(delay * 2, 60)
            else:
                raise


def _strip_code_fence(raw: str) -> str:
    """Strip ```json … ``` or ``` … ``` fences if present."""
    if "```json" in raw:
        raw = raw.split("```json")[1].split("```")[0]
    elif "```" in raw:
        raw = raw.split("```")[1].split("```")[0]
    return raw.strip()


def analyze_deal_structure(
    terms_text: str, memo_text: str, client
) -> Tuple[dict, str]:
    """
    First Claude API call: figure out the deal type and structure
    so we only extract applicable fields in the next step.

    Returns (deal_dict, prompt_version).
    """
    template, prompt_version = load_prompt("deal_analysis")
    prompt = template.format(
        terms_text=terms_text[:4000],
        memo_text=memo_text[:2000] if memo_text else "Not provided",
    )

    try:
        response = _claude_with_retry(
            client,
            model="claude-sonnet-4-20250514",
            max_tokens=512,
            messages=[{"role": "user", "content": prompt}]
        )
    except Exception as e:
        logger.error(
            "analyze_deal_structure: Claude API error: %s", e, exc_info=True,
        )
        raise ExtractionStageError(
            stage="deal_analysis",
            reason="api_error",
            message=f"Anthropic API call failed: {e}",
        )

    raw = response.content[0].text
    cleaned = _strip_code_fence(raw)
    try:
        parsed = json.loads(cleaned)
    except json.JSONDecodeError as e:
        excerpt = raw[:500] if raw else ""
        logger.error(
            "analyze_deal_structure: JSON decode failed (%s). Raw excerpt: %r",
            e, excerpt,
        )
        raise ExtractionStageError(
            stage="deal_analysis",
            reason="json_decode",
            message=f"Claude returned malformed JSON for deal analysis: {e}",
            raw_excerpt=excerpt,
        )

    try:
        validated = DealStructure.model_validate(parsed)
    except ValidationError as e:
        # Log full details server-side, surface a sanitized message to callers.
        logger.error(
            "analyze_deal_structure: Pydantic validation failed. Errors: %s. Raw parsed: %r",
            e.errors(), parsed,
        )
        raise ExtractionStageError(
            stage="deal_analysis",
            reason="schema_validation",
            message=(
                "Claude returned a deal-analysis JSON object that did not match "
                f"the expected schema ({len(e.errors())} validation error(s))."
            ),
        )

    return validated.model_dump(), prompt_version


def build_schema(deal: dict) -> dict:
    """Return only the fields applicable to this deal.

    Driven by FieldRegistry.fields_for_deal(deal) — DERIVED and LOOKUP
    field types are excluded since they aren't extraction targets
    (DERIVED is post-processed by the formatting layer; LOOKUP is
    resolved by the lender registry post-extraction).

    NOTE: LoanType is intentionally omitted. It is derived from the
    deal-analysis stage's `loan_program` (validated by the DealStructure
    Literal) and injected into raw_data by the pipeline after
    extract_fields. Re-adding it here would let Claude guess values
    like "Variable" from interest-rate context.
    """
    fields: dict = {}
    for d in FieldRegistry.fields_for_deal(deal):
        if d.data_type in ("DERIVED", "LOOKUP"):
            continue
        fields[d.field_name] = ""

    return fields


def canonical_output_fields() -> list:
    """The fixed, ordered superset of keys every extraction JSON emits.

    Derived from the registry (NOT hardcoded): all CSV-defined field names in
    CSV order, with the pipeline-injected ``LoanType`` inserted at the head of
    the "Loan Details" group (immediately before ``LoanAmountLong``). LoanType
    is the only output key that isn't a CSV row — it is classified by the
    deal-analysis stage and mirrored into the field output — so it must be
    spliced into the canonical order explicitly.

    Because this is registry-driven, adding/removing a CSV row updates the
    canonical schema automatically with no second edit here.
    """
    names = FieldRegistry.canonical_field_names()
    if "LoanType" in names:
        return names
    try:
        idx = names.index("LoanAmountLong")
    except ValueError:
        idx = len(names)
    names.insert(idx, "LoanType")
    return names


def project_to_canonical(formatted: Dict[str, str]) -> Dict[str, str]:
    """Project a formatted-data dict onto the canonical output schema.

    Returns a NEW dict containing exactly the canonical keys, in canonical
    order, filling any missing key with "". Keys outside the canonical set are
    dropped with a warn-log (there should be none in practice — every output
    key is either a CSV field or the injected LoanType, all of which are
    canonical). The operation is idempotent: projecting an already-canonical
    dict returns an equal dict.

    This is the single chokepoint that guarantees downstream consumers always
    receive the same keys in the same order regardless of deal shape, and that
    legacy (narrow-shape) rows come out with the same shape as new ones.
    """
    # Defensive: tolerate malformed historical blobs (None / non-dict) without
    # raising — a download must never 500 on a legacy row.
    if not isinstance(formatted, dict):
        formatted = {}
    canonical = canonical_output_fields()
    canonical_set = set(canonical)
    for key in formatted:
        if key not in canonical_set:
            logger.warning(
                "project_to_canonical: dropping non-canonical key %r", key,
            )
    result: Dict[str, str] = {}
    for key in canonical:
        val = formatted.get(key, "")
        # Enforce the contract: every value is a string, unused slots are "".
        # Legacy rows may store null or non-string values; coerce them so the
        # downloaded JSON is uniformly typed for downstream consumers.
        if val is None:
            val = ""
        elif not isinstance(val, str):
            val = str(val)
        result[key] = val
    return result


def extract_fields(
    terms_text: str, memo_text: str, schema: dict, deal: dict,
    ner_hints: str, client,
) -> Tuple[Dict[str, str], Dict[str, str], str]:
    """
    Second Claude API call: extract all relevant fields with NER hints injected.

    Returns (values, sources, prompt_version):
      - values: dict reconciled against the dynamic schema (unknown keys
        dropped, non-strings coerced, missing keys filled with "")
      - sources: parallel dict of paired `<key>_source` quotes from the v2
        prompt's process-supervision contract; same key set as `values`
      - prompt_version: the version tag of the field_extraction template used
    """
    schema_str = json.dumps(schema, indent=2)
    # NOTE: load_prompt resolves to the latest version, currently v2 — which
    # asks the model to return paired `<FieldName>_source` keys for every
    # schema key. The pipeline's quote-verification step depends on this
    # contract; if you pin back to v1, source dicts will be empty and the
    # `field_sources` UI block will disappear gracefully.
    template, prompt_version = load_prompt("field_extraction")
    prompt = template.format(
        deal_type=deal.get("deal_type", "Unknown"),
        loan_program=deal.get("loan_program", "Unknown"),
        ner_hints=ner_hints,
        terms_text=terms_text,
        memo_text=memo_text if memo_text else "Not provided",
        schema_str=schema_str,
    )

    try:
        response = _claude_with_retry(
            client,
            model="claude-sonnet-4-20250514",
            # Doubled for paired _source quotes per field (v2 prompt)
            max_tokens=8192,
            messages=[{"role": "user", "content": prompt}]
        )
    except Exception as e:
        logger.error(
            "extract_fields: Claude API error: %s", e, exc_info=True,
        )
        raise ExtractionStageError(
            stage="field_extraction",
            reason="api_error",
            message=f"Anthropic API call failed: {e}",
        )

    raw = response.content[0].text
    cleaned = _strip_code_fence(raw)
    try:
        parsed = json.loads(cleaned)
    except json.JSONDecodeError as e:
        excerpt = raw[:500] if raw else ""
        logger.error(
            "extract_fields: JSON decode failed (%s). Raw excerpt: %r",
            e, excerpt,
        )
        raise ExtractionStageError(
            stage="field_extraction",
            reason="json_decode",
            message=f"Claude returned malformed JSON for field extraction: {e}",
            raw_excerpt=excerpt,
        )

    if not isinstance(parsed, dict):
        logger.error(
            "extract_fields: Claude returned non-dict JSON (%s). Raw excerpt: %r",
            type(parsed).__name__, raw[:500] if raw else "",
        )
        raise ExtractionStageError(
            stage="field_extraction",
            reason="schema_validation",
            message=(
                "Claude returned a non-object JSON value for field extraction "
                f"(got {type(parsed).__name__})."
            ),
        )

    try:
        values, sources = validate_extracted_fields(parsed, set(schema.keys()))
    except Exception as e:
        logger.error(
            "extract_fields: validation failed: %s. Raw parsed keys: %s",
            e, list(parsed.keys())[:30],
        )
        raise ExtractionStageError(
            stage="field_extraction",
            reason="schema_validation",
            message=f"Field-extraction output failed validation: {e}",
        )

    return values, sources, prompt_version
