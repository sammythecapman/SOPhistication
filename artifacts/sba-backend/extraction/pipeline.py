"""
Core extraction pipeline orchestrator.
Runs all stages: PDF reading → NER → deal analysis → field extraction → validation → formatting.
"""

import os
import re
import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, Optional, Callable

import pdfplumber
import anthropic

from .ner_engine import load_ner_model, run_ner, merge_ner_results, format_ner_hints
from .schemas import analyze_deal_structure, build_schema, extract_fields
from .formatting import apply_field_formatting
from .regex_fallbacks import regex_extract_critical_fields
from .confidence import score_extracted_fields
from .errors import ExtractionStageError
from .prompts.registry import PROMPT_VERSIONS

logger = logging.getLogger(__name__)


def read_pdf(path: str) -> str:
    """Extract all text from a PDF file using pdfplumber."""
    text = ""
    try:
        with pdfplumber.open(path) as pdf:
            for i, page in enumerate(pdf.pages):
                page_text = page.extract_text()
                if page_text:
                    text += f"\n--- PAGE {i+1} ---\n{page_text}"
        return text.strip()
    except Exception as e:
        raise RuntimeError(f"Could not read PDF: {e}")


def run_extraction_pipeline(
    terms_path: str,
    memo_path: Optional[str],
    job_id: str,
    job_store: Dict[str, Any],
    on_stage: Optional[Callable] = None
) -> Dict[str, Any]:
    """
    Run the full extraction pipeline for the given PDF files.

    Args:
        terms_path: Path to the Terms & Conditions PDF
        memo_path: Path to the Credit Memo PDF (optional)
        job_id: Job ID for progress tracking
        job_store: Shared dict for job status updates
        on_stage: Optional callback(stage, stage_label, progress) for progress events

    Returns:
        Dict with extraction results
    """

    def update_stage(stage: str, stage_label: str, progress: int):
        if job_store is not None:
            job_store[job_id].update({
                "stage": stage,
                "stage_label": stage_label,
                "progress": progress,
            })
        if on_stage:
            on_stage(stage, stage_label, progress)

    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        raise RuntimeError("ANTHROPIC_API_KEY environment variable is not set")

    client = anthropic.Anthropic(api_key=api_key)

    # ── Stage 1: Read PDFs ──
    update_stage("reading_pdf", "Reading PDF documents", 5)
    terms_text = read_pdf(terms_path)
    if not terms_text:
        raise RuntimeError("Could not extract text from Terms & Conditions PDF. The file may be scanned/image-based.")

    memo_text = ""
    if memo_path and Path(memo_path).exists():
        try:
            memo_text = read_pdf(memo_path)
        except Exception:
            memo_text = ""

    # ── Stage 2: NER Preprocessing ──
    update_stage("running_ner", "Running NER analysis", 15)
    try:
        nlp = load_ner_model()
        ner_terms = run_ner(terms_text, nlp)
        ner_memo = run_ner(memo_text, nlp) if memo_text else None
        ner_entities = merge_ner_results(ner_terms, ner_memo)
        ner_hints = format_ner_hints(ner_entities)
    except Exception:
        ner_entities = {}
        ner_hints = ""

    # ── extraction_health tracking ──
    stage_failures: list = []

    # Capture which prompt versions this run is using. Even on stage failure
    # we know which template was loaded, since load_prompt runs before Claude.
    deal_analysis_version: str = PROMPT_VERSIONS.get("deal_analysis", "unknown")
    field_extraction_version: str = PROMPT_VERSIONS.get("field_extraction", "unknown")

    # ── Stage 3: Analyze Deal Structure ──
    update_stage("analyzing_deal", "Analyzing deal structure", 30)
    try:
        deal, deal_analysis_version = analyze_deal_structure(
            terms_text, memo_text, client,
        )
    except ExtractionStageError as e:
        logger.warning(
            "Pipeline degraded — deal_analysis failed (%s): %s",
            e.reason, e.message,
        )
        stage_failures.append(e.to_dict())
        deal = {}

    # ── Build Schema ──
    schema = build_schema(deal)

    # ── Stage 4: Extract Fields ──
    update_stage("extracting_fields", "Extracting fields with AI", 50)
    raw_sources: Dict[str, str] = {}
    try:
        raw_data, raw_sources, field_extraction_version = extract_fields(
            terms_text, memo_text, schema, deal, ner_hints, client,
        )
    except ExtractionStageError as e:
        logger.warning(
            "Pipeline degraded — field_extraction failed (%s): %s",
            e.reason, e.message,
        )
        stage_failures.append(e.to_dict())
        raw_data = {}
        raw_sources = {}

    # ── Apply regex fallbacks for critical fields ──
    # Mark regex-filled fields with the sentinel "[regex_fallback]" source so
    # downstream code (and the UI) can distinguish them from genuine model
    # citations and from missing data.
    regex_results = regex_extract_critical_fields(terms_text)
    for field, value in regex_results.items():
        if field not in raw_data or not raw_data.get(field):
            raw_data[field] = value
            raw_sources[field] = "[regex_fallback]"

    # ── Stage 5: Confidence Scoring ──
    update_stage("validating", "Scoring extraction confidence", 75)
    confidence_scores: dict = {}
    ner_warnings: list = []
    if ner_entities:
        try:
            import db as _db
            learned = _db.get_learned_suppressions()
        except Exception:
            learned = {}
        confidence_scores = score_extracted_fields(
            raw_data, ner_entities, terms_text, learned_suppressions=learned
        )
        # Build legacy ner_warnings list from RED scores for backward compat
        ner_warnings = [
            f"⛔ HALLUCINATION RISK: '{f}' value '{s['value']}' was NOT FOUND in source text."
            for f, s in confidence_scores.items()
            if s["confidence_tier"] == "red"
        ]

    # ── Source citations — process supervision ──
    # Build the full per-field citations dict (covers every populated field,
    # including non-scored ones like amounts/dates/addresses), then merge the
    # subset for SCORED_FIELDS into confidence_scores so the UI's existing
    # confidence cards can show them too.
    field_sources: Dict[str, Dict[str, Any]] = {}
    for field, value in raw_data.items():
        if not value or not str(value).strip():
            continue
        quote = raw_sources.get(field, "") or ""
        if quote == "[regex_fallback]":
            verified: Optional[bool] = None
        elif quote:
            verified = _verify_quote_in_source(
                quote, str(value), terms_text, memo_text,
            )
        else:
            verified = None
        field_sources[field] = {"quote": quote, "verified": verified}

    for field, entry in confidence_scores.items():
        src = field_sources.get(field, {"quote": "", "verified": None})
        # `model_cited_source` shows the actual quote (or "" if regex-filled
        # / no model citation). The sentinel string isn't user-facing.
        entry["model_cited_source"] = (
            src["quote"] if src["quote"] != "[regex_fallback]" else ""
        )
        entry["cited_source_in_document"] = src["verified"]

    # ── Stage 6: Apply Formatting ──
    update_stage("formatting", "Applying field formatting", 90)
    formatted_data = apply_field_formatting(raw_data)

    # ── Compile Results ──
    found = sum(1 for v in formatted_data.values() if v and str(v).strip())
    total = len(formatted_data)
    completion_pct = round((found / total) * 100, 1) if total > 0 else 0.0

    extraction_health = {
        "degraded": len(stage_failures) > 0,
        "stage_failures": stage_failures,
    }

    return {
        "extracted_at": datetime.now().isoformat(),
        "terms_filename": Path(terms_path).name,
        "credit_memo_filename": Path(memo_path).name if memo_path else None,
        "deal_structure": deal,
        "raw_data": raw_data,
        "formatted_data": formatted_data,
        "ner_warnings": ner_warnings,
        "confidence_scores": confidence_scores,
        "field_sources": field_sources,
        "extraction_health": extraction_health,
        "prompt_versions": {
            "deal_analysis": deal_analysis_version,
            "field_extraction": field_extraction_version,
        },
        "summary": {
            "fields_populated": found,
            "fields_total": total,
            "fields_empty": total - found,
            "completion_percentage": completion_pct,
        }
    }


# ──────────────────────────────────────────────
# Quote-verification helper (process supervision)
# ──────────────────────────────────────────────

_WS_RE = re.compile(r"\s+")


def _substring_after_collapse(needle: str, *texts: str) -> bool:
    """Whitespace-collapsed, case-insensitive substring check across texts."""
    if not needle:
        return False
    n = _WS_RE.sub(" ", needle).strip().lower()
    if not n:
        return False
    for text in texts:
        if not text:
            continue
        haystack = _WS_RE.sub(" ", text).lower()
        if n in haystack:
            return True
    return False


def _verify_quote_in_source(
    quote: str, value: str, *texts: str,
) -> Optional[bool]:
    """
    Check whether the model's citation is supported by the source documents.

    Performs a two-tier substring check, both whitespace-collapsed and
    case-insensitive (PDF line wrapping and inconsistent casing in legal
    documents would otherwise cause spurious mismatches):

      Tier 1 — exact citation: does `quote` appear in any of `texts`?
      Tier 2 — value fallback: does `value` (the extracted datum, with the
               citation's label/punctuation stripped away) appear in any of
               `texts`?

    The fallback is necessary because models routinely paraphrase table
    cells in their citations — e.g. quoting `"Lender: Pierpoint Bank"`
    when the PDF actually renders it as `"Lender    Pierpoint Bank"` (tab
    or column-aligned). Without the fallback, every such field would be
    falsely marked Unverified Quote even though the underlying datum is
    clearly supported.

    If the quote ends with the truncation sentinel "…" (added by the
    validator when a quote exceeds 200 chars), we strip it before matching.

    Returns:
      - True  if either tier matches
      - False if the quote is non-empty AND neither tier matches
      - None  if the quote is empty/whitespace-only (nothing to verify)
    """
    if not quote or not quote.strip():
        return None
    # Strip the ellipsis truncation marker so truncated quotes can verify.
    quote_stripped = quote[:-1] if quote.endswith("…") else quote
    if _substring_after_collapse(quote_stripped, *texts):
        return True
    # Fallback: the model often paraphrases citations; if the actual
    # extracted value is a substring of the source, the citation is
    # considered supported (even if the model wrote it with extra label
    # punctuation or surrounding whitespace).
    if value and value.strip() and _substring_after_collapse(value, *texts):
        return True
    return False
