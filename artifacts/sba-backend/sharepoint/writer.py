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
        # Document library (drive) to drop JSON into. Dropoff is its own library
        # on the root site, not a folder inside the default "Documents" library.
        self.library_name = os.environ.get("SHAREPOINT_LIBRARY_NAME", "Dropoff")
        self.graph_base = "https://graph.microsoft.com/v1.0"

    @property
    def is_configured(self) -> bool:
        return self.auth.is_configured

    def _get_site_id(self) -> str:
        """Get the SharePoint site ID."""
        import requests

        site_url = self.site_url.rstrip("/")
        remainder = site_url.replace("https://", "").replace("http://", "")
        parts = remainder.split("/", 1)
        hostname = parts[0]
        site_path = parts[1].strip("/") if len(parts) > 1 else ""

        if site_path:
            url = f"{self.graph_base}/sites/{hostname}:/{site_path}"
        else:
            # Root site of the host — no path segment (e.g. kylejohnsonlaw.sharepoint.com)
            url = f"{self.graph_base}/sites/{hostname}"

        response = requests.get(url, headers=self.auth.get_headers())
        response.raise_for_status()
        return response.json()["id"]

    def _get_drive_id(self, site_id: str, library_name: str) -> str:
        """Resolve a document library (drive) on the site by its display name."""
        import requests

        url = f"{self.graph_base}/sites/{site_id}/drives"
        response = requests.get(url, headers=self.auth.get_headers())
        response.raise_for_status()
        drives = response.json().get("value", [])
        for d in drives:
            if d.get("name", "").lower() == library_name.lower():
                return d["id"]
        available = ", ".join(repr(d.get("name")) for d in drives) or "(none)"
        raise RuntimeError(
            f"SharePoint library {library_name!r} not found on site. "
            f"Available libraries: {available}"
        )

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
                        subfolder: Optional[str] = None) -> Dict:
        """
        Upload the formatted JSON into the configured document library
        (self.library_name, default "Dropoff"), at the library root or an
        optional subfolder inside it.
        """
        import requests
        from datetime import datetime

        site_id = self._get_site_id()
        drive_id = self._get_drive_id(site_id, self.library_name)

        formatted = extraction_data.get("formatted_data", {})
        borrower = formatted.get("Borrower1Name", "Unknown").replace(" ", "_")
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"SBA_Extraction_{borrower}_{timestamp}.json"

        item_path = f"{subfolder.strip('/')}/{filename}" if subfolder else filename
        url = f"{self.graph_base}/drives/{drive_id}/root:/{item_path}:/content"

        json_bytes = json.dumps(extraction_data.get("formatted_data", {}), indent=2).encode("utf-8")
        headers = self.auth.get_headers()
        headers["Content-Type"] = "application/octet-stream"
        response = requests.put(url, headers=headers, data=json_bytes)
        response.raise_for_status()
        return {"filename": filename, "library": self.library_name, "item": response.json()}
