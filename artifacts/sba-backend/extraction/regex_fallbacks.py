"""
Regex-based fallback extraction for critical fields that Claude sometimes misses.
"""

import re
from typing import Dict


def regex_extract_critical_fields(text: str) -> Dict[str, str]:
    """
    Regex fallback extraction for LoanNumber and MaturityDate.
    These are critical fields that Claude sometimes misses.
    Returns a dict of field_name -> value for any fields found.
    """
    result: Dict[str, str] = {}

    # ── SBA Loan Number ──
    # Matches "SBA Loan #", "Loan No.", "Loan Number", "Note No.", and dash-formatted numbers.
    sba_number_patterns = [
        r'SBA\s+[Ll]oan\s+[Nn]umber\s*[:=]?\s*([0-9\-]{8,15})',
        r'SBA\s+[Ll]oan\s+#\s*([0-9\-]{8,15})',
        r'(?:SBA\s+)?[Aa]pproval\s+[Nn]o(?:\.|umber)?\s*[:=]?\s*([0-9\-]{8,15})',
        r'SBA\s+[Nn]o\.?\s*[:=]?\s*([0-9\-]{8,15})',
    ]

    if "SBALoanNumber" not in result:
        for pattern in sba_number_patterns:
            match = re.search(pattern, text)
            if match:
                result["SBALoanNumber"] = match.group(1).strip()
                break

    # ── Maturity Date ──
    maturity_patterns = [
        r'[Mm]ature[sd]?\s+(?:on\s+)?([A-Z][a-z]+ \d{1,2},\s*\d{4})',
        r'[Mm]aturity\s+[Dd]ate\s*[:=]?\s*([A-Z][a-z]+ \d{1,2},\s*\d{4})',
        r'[Mm]aturity\s+[Dd]ate\s*[:=]?\s*(\d{1,2}/\d{1,2}/\d{4})',
        r'(?:due|payable)\s+(?:in\s+full\s+)?(?:on\s+)?([A-Z][a-z]+ \d{1,2},\s*\d{4})',
        r'final\s+(?:payment|maturity)\s+(?:date\s+)?(?:of\s+)?([A-Z][a-z]+ \d{1,2},\s*\d{4})',
        r'[Mm]aturity\s+[Dd]ate[:\s]+(\d{2}/\d{2}/\d{4})',
    ]

    for pattern in maturity_patterns:
        match = re.search(pattern, text)
        if match:
            result["MaturityDate"] = match.group(1).strip()
            break

    # ── Initial Payment Date ──
    payment_date_patterns = [
        r'[Ff]irst\s+(?:monthly\s+)?payment\s+(?:is\s+)?due\s+(?:on\s+)?([A-Z][a-z]+ \d{1,2},\s*\d{4})',
        r'[Ii]nitial\s+[Pp]ayment\s+[Dd]ate\s*[:=]?\s*([A-Z][a-z]+ \d{1,2},\s*\d{4})',
        r'[Ff]irst\s+[Pp]ayment\s+[Dd]ate\s*[:=]?\s*(\d{1,2}/\d{1,2}/\d{4})',
    ]

    if "InitialPaymentDate" not in result:
        for pattern in payment_date_patterns:
            match = re.search(pattern, text)
            if match:
                result["InitialPaymentDate"] = match.group(1).strip()
                break

    return result
