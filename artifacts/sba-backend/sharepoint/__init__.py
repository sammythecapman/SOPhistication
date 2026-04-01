"""
SharePoint integration package.

Exports the factory functions used by all endpoints.
Use these instead of importing SharePointWriter/Reader directly.

Usage:
    from sharepoint import get_writer, get_reader, get_status

    writer = get_writer()   # MockSharePointWriter or SharePointWriter
    reader = get_reader()   # MockSharePointReader or SharePointReader
    status = get_status()   # dict describing current mode
"""

from .factory import get_writer, get_reader, get_status

__all__ = ["get_writer", "get_reader", "get_status"]
