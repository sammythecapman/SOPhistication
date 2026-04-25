"""
Versioned prompt registry.

Each prompt lives in `extraction/prompts/<name>/vN.txt` as plain text with
`{placeholder}`-style fields. `load_prompt(name, version="latest")` returns the
template text and the resolved version string so callers can persist exactly
which prompt produced an extraction.
"""

import logging
import re
from pathlib import Path
from typing import Dict, Tuple

logger = logging.getLogger(__name__)

PROMPTS_DIR = Path(__file__).parent

_VERSION_PATTERN = re.compile(r"^v(\d+)\.txt$")


def _list_versions(prompt_dir: Path) -> list[tuple[int, Path]]:
    """Return [(version_number, file_path), ...] sorted ascending by version."""
    versions: list[tuple[int, Path]] = []
    for entry in prompt_dir.iterdir():
        if not entry.is_file():
            continue
        m = _VERSION_PATTERN.match(entry.name)
        if not m:
            continue
        versions.append((int(m.group(1)), entry))
    versions.sort(key=lambda t: t[0])
    return versions


def _resolve_latest(prompt_dir: Path) -> tuple[str, Path]:
    versions = _list_versions(prompt_dir)
    if not versions:
        raise FileNotFoundError(
            f"No versioned prompt files (vN.txt) found in {prompt_dir}"
        )
    n, path = versions[-1]
    return f"v{n}", path


def load_prompt(name: str, version: str = "latest") -> Tuple[str, str]:
    """
    Load a prompt template by name and version.

    Args:
        name: prompt directory name (e.g. "deal_analysis")
        version: "latest" or an explicit version like "v1"

    Returns:
        (prompt_template_text, resolved_version)

    Raises:
        FileNotFoundError if the prompt directory or version does not exist.
    """
    prompt_dir = PROMPTS_DIR / name
    if not prompt_dir.is_dir():
        raise FileNotFoundError(f"Prompt '{name}' not found at {prompt_dir}")

    if version == "latest":
        resolved, path = _resolve_latest(prompt_dir)
    else:
        path = prompt_dir / f"{version}.txt"
        if not path.is_file():
            raise FileNotFoundError(
                f"Prompt '{name}' has no version '{version}' (looked for {path})"
            )
        resolved = version

    return path.read_text(encoding="utf-8"), resolved


def _build_versions_snapshot() -> Dict[str, str]:
    """Build a {name: latest_version} dict for all known prompts at import time."""
    snapshot: Dict[str, str] = {}
    if not PROMPTS_DIR.is_dir():
        return snapshot
    for entry in PROMPTS_DIR.iterdir():
        if not entry.is_dir() or entry.name.startswith("_"):
            continue
        try:
            resolved, _ = _resolve_latest(entry)
            snapshot[entry.name] = resolved
        except FileNotFoundError:
            continue
    return snapshot


PROMPT_VERSIONS: Dict[str, str] = _build_versions_snapshot()
logger.info("Loaded prompt versions: %s", PROMPT_VERSIONS)
