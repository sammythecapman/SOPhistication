"""
Mock SharePoint writer — drop-in replacement for SharePointWriter.

Writes extraction results to the local mock_sharepoint_library/ folder
instead of calling Microsoft Graph API.  The on-disk layout mirrors what
the real writer would create in SharePoint:

  mock_sharepoint_library/
    list_items.json               ← append-only list of pushed items
    SBA Extractions/
      SBA_Extraction_<Borrower>_<timestamp>.json
"""

import json
from datetime import datetime
from pathlib import Path
from typing import Any, Dict

_MOCK_ROOT = Path(__file__).parent.parent / "mock_sharepoint_library"


class MockSharePointWriter:
    """Writes extraction results to local JSON files (mock SharePoint)."""

    is_configured = True
    mode = "mock"

    def __init__(self):
        _MOCK_ROOT.mkdir(parents=True, exist_ok=True)

    # ──────────────────────────────────────────
    # Public API — matches SharePointWriter
    # ──────────────────────────────────────────

    def push_to_list(self, extraction_data: Dict[str, Any]) -> Dict:
        """
        Append a row to the mock SharePoint List (list_items.json).
        Returns the new item dict.
        """
        formatted = extraction_data.get("formatted_data", {})
        deal = extraction_data.get("deal_structure", {})

        item = {
            "id": f"mock-{datetime.now().strftime('%Y%m%d%H%M%S%f')}",
            "createdDateTime": datetime.now().isoformat(),
            "fields": {
                "Title": formatted.get("Borrower1Name", "Unknown Borrower"),
                "DealType": deal.get("deal_type", ""),
                "LoanProgram": deal.get("loan_program", ""),
                "LoanAmount": formatted.get("LoanAmountShort", ""),
                "MaturityDate": formatted.get("MaturityDate", ""),
                "LenderName": formatted.get("LenderName", ""),
                "BorrowerName": formatted.get("Borrower1Name", ""),
                "SBALoanNumber": formatted.get("SBALoanNumber", ""),
                "CompletionPct": str(extraction_data.get("completion_pct", 0)),
                "TermsFilename": extraction_data.get("terms_filename", ""),
                "ExtractionId": str(extraction_data.get("id", "")),
            },
        }

        list_file = _MOCK_ROOT / "list_items.json"
        items = _load_json(list_file, default=[])
        items.append(item)
        _write_json(list_file, items)

        print(f"📋 [Mock SP] List item added: {item['id']}")
        return item

    def push_to_folder(
        self,
        extraction_data: Dict[str, Any],
        folder_name: str = "SBA Extractions",
    ) -> Dict:
        """
        Write a JSON file to mock_sharepoint_library/<folder_name>/.
        Returns metadata dict mimicking Graph API response.
        """
        formatted = extraction_data.get("formatted_data", {})
        borrower = formatted.get("Borrower1Name", "Unknown").replace(" ", "_")
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"SBA_Extraction_{borrower}_{timestamp}.json"

        folder_path = _MOCK_ROOT / folder_name
        folder_path.mkdir(parents=True, exist_ok=True)
        file_path = folder_path / filename

        _write_json(file_path, formatted)

        item = {
            "id": f"{folder_name}/{filename}",
            "name": filename,
            "folder": folder_name,
            "size": file_path.stat().st_size,
            "createdDateTime": datetime.now().isoformat(),
            "webUrl": f"mock://sharepoint/{folder_name}/{filename}",
        }
        print(f"📁 [Mock SP] File written: {folder_name}/{filename}")
        return {"filename": filename, "item": item}


# ──────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────

def _load_json(path: Path, default):
    if path.exists():
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return default
    return default


def _write_json(path: Path, data) -> None:
    path.write_text(json.dumps(data, indent=2, default=str), encoding="utf-8")
