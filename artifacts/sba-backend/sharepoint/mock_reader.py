"""
Mock SharePoint reader — drop-in replacement for SharePointReader.

Reads from the local mock_sharepoint_library/ folder that mock_writer.py
populates.  Method signatures match SharePointReader exactly so the
factory can swap them transparently.
"""

import json
import shutil
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

_MOCK_ROOT = Path(__file__).parent.parent / "mock_sharepoint_library"


class MockSharePointReader:
    """Reads from local mock SharePoint library (mock mode)."""

    is_configured = True
    mode = "mock"

    def __init__(self):
        _MOCK_ROOT.mkdir(parents=True, exist_ok=True)

    # ──────────────────────────────────────────
    # Public API — matches SharePointReader
    # ──────────────────────────────────────────

    def list_folders(self, library_name: str = "Documents") -> List[Dict]:
        """
        Return all top-level folders (and the list_items pseudo-file) inside
        mock_sharepoint_library/.
        """
        items = []

        if not _MOCK_ROOT.exists():
            return items

        for entry in sorted(_MOCK_ROOT.iterdir()):
            if entry.name.startswith("."):
                continue
            if entry.is_dir():
                items.append({
                    "id": entry.name,
                    "name": entry.name,
                    "type": "folder",
                    "size": _dir_size(entry),
                    "modified": _mtime(entry),
                    "download_url": "",
                })
            elif entry.name == "list_items.json":
                items.append({
                    "id": "list_items.json",
                    "name": "list_items.json (SP List)",
                    "type": "file",
                    "size": entry.stat().st_size,
                    "modified": _mtime(entry),
                    "download_url": "",
                })

        return items

    def list_pdfs_in_folder(self, folder_id: str) -> List[Dict]:
        """
        List JSON files inside mock_sharepoint_library/<folder_id>/.
        In the real implementation this lists PDFs; in mock it lists JSONs
        (which are what the writer stores).
        """
        folder_path = _MOCK_ROOT / folder_id
        if not folder_path.exists() or not folder_path.is_dir():
            return []

        items = []
        for entry in sorted(folder_path.iterdir(), key=lambda e: e.stat().st_mtime, reverse=True):
            if entry.is_file() and entry.suffix in (".json", ".pdf"):
                items.append({
                    "id": f"{folder_id}/{entry.name}",
                    "name": entry.name,
                    "size": entry.stat().st_size,
                    "modified": _mtime(entry),
                    "download_url": "",
                })
        return items

    def download_file(self, file_id: str, dest_path: str) -> str:
        """
        Copy a file from mock_sharepoint_library/<file_id> to dest_path.
        file_id is the relative path from _MOCK_ROOT (e.g. 'SBA Extractions/foo.json').
        """
        src = _MOCK_ROOT / file_id
        if not src.exists():
            raise FileNotFoundError(f"Mock SP file not found: {file_id}")
        shutil.copy2(str(src), dest_path)
        return dest_path

    def list_items(self) -> List[Dict]:
        """Return all items from the mock SharePoint List (list_items.json)."""
        list_file = _MOCK_ROOT / "list_items.json"
        if not list_file.exists():
            return []
        try:
            return json.loads(list_file.read_text(encoding="utf-8"))
        except Exception:
            return []


# ──────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────

def _mtime(path: Path) -> str:
    try:
        return datetime.fromtimestamp(path.stat().st_mtime).isoformat()
    except Exception:
        return ""


def _dir_size(path: Path) -> int:
    try:
        return sum(f.stat().st_size for f in path.rglob("*") if f.is_file())
    except Exception:
        return 0
