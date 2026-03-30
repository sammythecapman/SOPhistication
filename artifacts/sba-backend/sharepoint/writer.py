"""
SharePoint file writer — push extraction results back to SharePoint.
Supports writing to a SharePoint List or to a document library folder.
"""

import json
import os
from typing import Dict, Any, Optional
from .auth import SharePointAuth


class SharePointWriter:
    """Write extraction results to SharePoint Online via Microsoft Graph API."""

    def __init__(self):
        self.auth = SharePointAuth()
        self.site_url = os.environ.get("SHAREPOINT_SITE_URL", "")
        self.list_name = os.environ.get("SHAREPOINT_LIST_NAME", "SBA Extractions")
        self.graph_base = "https://graph.microsoft.com/v1.0"

    @property
    def is_configured(self) -> bool:
        return self.auth.is_configured

    def _get_site_id(self) -> str:
        """Get the SharePoint site ID."""
        import requests

        site_url = self.site_url.rstrip("/")
        parts = site_url.replace("https://", "").split("/", 1)
        hostname = parts[0]
        site_path = parts[1] if len(parts) > 1 else ""

        url = f"{self.graph_base}/sites/{hostname}:/{site_path}"
        response = requests.get(url, headers=self.auth.get_headers())
        response.raise_for_status()
        return response.json()["id"]

    def push_to_list(self, extraction_data: Dict[str, Any]) -> Dict:
        """
        Push extracted fields as a new row in a SharePoint List.
        Creates the list if it doesn't exist.
        """
        import requests

        site_id = self._get_site_id()
        formatted = extraction_data.get("formatted_data", {})
        deal = extraction_data.get("deal_structure", {})
        summary = extraction_data.get("summary", {})

        # Build list item fields
        fields = {
            "Title": formatted.get("Borrower1Name", "Unknown Borrower"),
            "DealType": deal.get("deal_type", ""),
            "LoanProgram": deal.get("loan_program", ""),
            "LoanAmount": formatted.get("LoanAmountShort", ""),
            "MaturityDate": formatted.get("MaturityDate", ""),
            "LenderName": formatted.get("LenderName", ""),
            "BorrowerName": formatted.get("Borrower1Name", ""),
            "SBALoanNumber": formatted.get("SBALoanNumber", ""),
            "CompletionPct": str(summary.get("completion_percentage", 0)),
            "TermsFilename": extraction_data.get("terms_filename", ""),
        }

        # Add all other formatted fields
        for k, v in formatted.items():
            if k not in fields and v:
                # SharePoint field names can't have special chars
                safe_key = k.replace("/", "_").replace(" ", "_")
                fields[safe_key] = str(v)[:255]  # SP list text field limit

        url = f"{self.graph_base}/sites/{site_id}/lists/{self.list_name}/items"
        payload = {"fields": fields}

        response = requests.post(url, headers=self.auth.get_headers(), json=payload)
        response.raise_for_status()
        return response.json()

    def push_to_folder(self, extraction_data: Dict[str, Any],
                        folder_name: str = "SBA Extractions") -> Dict:
        """
        Upload the formatted JSON file to a SharePoint document library folder.
        """
        import requests
        from datetime import datetime

        site_id = self._get_site_id()
        formatted = extraction_data.get("formatted_data", {})
        borrower = formatted.get("Borrower1Name", "Unknown").replace(" ", "_")
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"SBA_Extraction_{borrower}_{timestamp}.json"

        url = (
            f"{self.graph_base}/sites/{site_id}/drive/root:/{folder_name}/{filename}:/content"
        )
        json_bytes = json.dumps(extraction_data.get("formatted_data", {}), indent=2).encode("utf-8")

        headers = self.auth.get_headers()
        headers["Content-Type"] = "application/octet-stream"
        response = requests.put(url, headers=headers, data=json_bytes)
        response.raise_for_status()
        return {"filename": filename, "item": response.json()}
