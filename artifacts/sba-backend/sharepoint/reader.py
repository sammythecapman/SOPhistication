"""
SharePoint file reader — browse and download files from SharePoint document libraries.
"""

import os
from typing import List, Dict, Optional
from .auth import SharePointAuth


class SharePointReader:
    """Read files from SharePoint Online via Microsoft Graph API."""

    def __init__(self):
        self.auth = SharePointAuth()
        self.site_url = os.environ.get("SHAREPOINT_SITE_URL", "")
        self.graph_base = "https://graph.microsoft.com/v1.0"

    @property
    def is_configured(self) -> bool:
        return self.auth.is_configured

    def _get_site_id(self) -> str:
        """Get the SharePoint site ID from the site URL."""
        import requests

        site_url = self.site_url.rstrip("/")
        # Extract hostname and site path
        parts = site_url.replace("https://", "").split("/", 1)
        hostname = parts[0]
        site_path = parts[1] if len(parts) > 1 else ""

        url = f"{self.graph_base}/sites/{hostname}:/{site_path}"
        response = requests.get(url, headers=self.auth.get_headers())
        response.raise_for_status()
        return response.json()["id"]

    def list_folders(self, library_name: str = "Documents") -> List[Dict]:
        """List folders in a SharePoint document library."""
        import requests

        site_id = self._get_site_id()
        url = f"{self.graph_base}/sites/{site_id}/drives"
        response = requests.get(url, headers=self.auth.get_headers())
        response.raise_for_status()

        drives = response.json().get("value", [])
        target_drive = None
        for drive in drives:
            if drive.get("name", "").lower() == library_name.lower():
                target_drive = drive
                break

        if not target_drive:
            target_drive = drives[0] if drives else None

        if not target_drive:
            return []

        drive_id = target_drive["id"]
        url = f"{self.graph_base}/drives/{drive_id}/root/children"
        response = requests.get(url, headers=self.auth.get_headers())
        response.raise_for_status()

        items = response.json().get("value", [])
        return [
            {
                "id": item["id"],
                "name": item["name"],
                "type": "folder" if "folder" in item else "file",
                "size": item.get("size", 0),
                "modified": item.get("lastModifiedDateTime", ""),
                "download_url": item.get("@microsoft.graph.downloadUrl", ""),
            }
            for item in items
        ]

    def list_pdfs_in_folder(self, folder_id: str) -> List[Dict]:
        """List PDF files in a specific folder."""
        import requests

        site_id = self._get_site_id()
        url = f"{self.graph_base}/sites/{site_id}/drive/items/{folder_id}/children"
        response = requests.get(url, headers=self.auth.get_headers())
        response.raise_for_status()

        items = response.json().get("value", [])
        return [
            {
                "id": item["id"],
                "name": item["name"],
                "size": item.get("size", 0),
                "modified": item.get("lastModifiedDateTime", ""),
                "download_url": item.get("@microsoft.graph.downloadUrl", ""),
            }
            for item in items
            if item["name"].lower().endswith(".pdf")
        ]

    def download_file(self, file_id: str, dest_path: str) -> str:
        """Download a file from SharePoint to a local path."""
        import requests

        site_id = self._get_site_id()
        url = f"{self.graph_base}/sites/{site_id}/drive/items/{file_id}/content"
        response = requests.get(url, headers=self.auth.get_headers(), allow_redirects=True)
        response.raise_for_status()

        with open(dest_path, "wb") as f:
            f.write(response.content)

        return dest_path
