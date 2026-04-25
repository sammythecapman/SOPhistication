"""
Custom exceptions raised by the extraction pipeline.

These are surfaced through `extraction_health` on the API response so that
silent partial failures (e.g. malformed Claude JSON) become visible to the
reviewer instead of looking like "the AI just couldn't find the field".
"""

from typing import Optional, Dict, Any


class ExtractionStageError(Exception):
    """
    Raised when a stage of the extraction pipeline fails in a way that
    *can* be recovered from (the pipeline continues with degraded output)
    but *must* be reported to the caller.

    Attributes:
        stage: which pipeline stage failed (e.g. "deal_analysis", "field_extraction")
        reason: short machine code for the failure (e.g. "json_decode", "api_error")
        message: human-readable explanation
        raw_excerpt: optional excerpt of the raw upstream response (truncated)
    """

    def __init__(
        self,
        stage: str,
        reason: str,
        message: str,
        raw_excerpt: Optional[str] = None,
    ):
        super().__init__(f"[{stage}/{reason}] {message}")
        self.stage = stage
        self.reason = reason
        self.message = message
        self.raw_excerpt = raw_excerpt

    def to_dict(self) -> Dict[str, Any]:
        payload: Dict[str, Any] = {
            "stage": self.stage,
            "reason": self.reason,
            "message": self.message,
        }
        if self.raw_excerpt is not None:
            payload["raw_excerpt"] = self.raw_excerpt
        return payload
