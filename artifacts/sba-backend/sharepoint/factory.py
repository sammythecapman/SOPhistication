"""
SharePoint factory — returns mock or real SharePoint classes.

Decision logic (checked in order):
  1. SHAREPOINT_MODE=mock  → always return mock classes
  2. Any of the required real credentials are missing → return mock classes
  3. All credentials present and mode is not "mock" → return real classes

Required real credentials:
  SHAREPOINT_CLIENT_ID, SHAREPOINT_CLIENT_SECRET,
  SHAREPOINT_TENANT_ID,  SHAREPOINT_SITE_URL
"""

import os
from typing import Literal

_REQUIRED_VARS = (
    "SHAREPOINT_CLIENT_ID",
    "SHAREPOINT_CLIENT_SECRET",
    "SHAREPOINT_TENANT_ID",
    "SHAREPOINT_SITE_URL",
)


def _use_mock() -> bool:
    if os.environ.get("SHAREPOINT_MODE", "").lower() == "mock":
        return True
    return not all(os.environ.get(v) for v in _REQUIRED_VARS)


def get_writer():
    """
    Return a SharePointWriter (real) or MockSharePointWriter (mock).
    Both expose: push_to_list(extraction_data), push_to_folder(extraction_data, folder_name).
    """
    if _use_mock():
        from .mock_writer import MockSharePointWriter
        return MockSharePointWriter()
    from .writer import SharePointWriter
    return SharePointWriter()


def get_reader():
    """
    Return a SharePointReader (real) or MockSharePointReader (mock).
    Both expose: list_folders(), list_pdfs_in_folder(folder_id), download_file(file_id, dest_path).
    """
    if _use_mock():
        from .mock_reader import MockSharePointReader
        return MockSharePointReader()
    from .reader import SharePointReader
    return SharePointReader()


def get_status() -> dict:
    """
    Return a status dict describing the current SharePoint mode and configuration.
    Used by the /api/sharepoint/status endpoint.
    """
    mock = _use_mock()
    mode_env = os.environ.get("SHAREPOINT_MODE", "")
    missing = [v for v in _REQUIRED_VARS if not os.environ.get(v)]

    if mock:
        if mode_env.lower() == "mock":
            reason = "SHAREPOINT_MODE=mock is set — using local mock library."
        else:
            reason = (
                f"Missing credentials ({', '.join(missing)}) — "
                "falling back to mock mode automatically."
            )
        return {
            "configured": True,
            "mode": "mock",
            "message": f"SharePoint running in mock mode. {reason}",
            "missing_vars": missing,
        }

    return {
        "configured": True,
        "mode": "live",
        "message": "SharePoint integration ready — connected to live tenant.",
        "missing_vars": [],
    }
