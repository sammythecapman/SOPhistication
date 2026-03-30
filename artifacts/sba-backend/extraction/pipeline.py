"""
Core extraction pipeline orchestrator.
Runs all stages: PDF reading → NER → deal analysis → field extraction → validation → formatting.
"""

import os
import json
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, Optional, Callable

import pdfplumber
import anthropic

from .ner_engine import load_ner_model, run_ner, merge_ner_results, format_ner_hints, validate_extraction_against_ner
from .schemas import analyze_deal_structure, build_schema, extract_fields
from .formatting import apply_field_formatting
from .regex_fallbacks import regex_extract_critical_fields


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

    # ── Stage 3: Analyze Deal Structure ──
    update_stage("analyzing_deal", "Analyzing deal structure", 30)
    deal = analyze_deal_structure(terms_text, memo_text, client)

    # ── Build Schema ──
    schema = build_schema(deal)

    # ── Stage 4: Extract Fields ──
    update_stage("extracting_fields", "Extracting fields with AI", 50)
    raw_data = extract_fields(terms_text, memo_text, schema, deal, ner_hints, client)

    if not raw_data:
        raise RuntimeError("Field extraction failed — no data returned from AI model")

    # ── Apply regex fallbacks for critical fields ──
    regex_results = regex_extract_critical_fields(terms_text)
    for field, value in regex_results.items():
        if field not in raw_data or not raw_data.get(field):
            raw_data[field] = value

    # ── Stage 5: Validate ──
    update_stage("validating", "Validating extracted data", 75)
    ner_warnings = []
    if ner_entities:
        ner_warnings = validate_extraction_against_ner(raw_data, ner_entities)

    # ── Stage 6: Apply Formatting ──
    update_stage("formatting", "Applying field formatting", 90)
    formatted_data = apply_field_formatting(raw_data)

    # ── Compile Results ──
    found = sum(1 for v in formatted_data.values() if v and str(v).strip())
    total = len(formatted_data)
    completion_pct = round((found / total) * 100, 1) if total > 0 else 0.0

    return {
        "extracted_at": datetime.now().isoformat(),
        "terms_filename": Path(terms_path).name,
        "credit_memo_filename": Path(memo_path).name if memo_path else None,
        "deal_structure": deal,
        "raw_data": raw_data,
        "formatted_data": formatted_data,
        "ner_warnings": ner_warnings,
        "summary": {
            "fields_populated": found,
            "fields_total": total,
            "fields_empty": total - found,
            "completion_percentage": completion_pct,
        }
    }
