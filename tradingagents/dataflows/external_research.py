"""External research ingestion vendor — the AI-OS upload path.

Reads the newest file the user drops into the ingest folder
(``TRADINGAGENTS_EXTERNAL_RESEARCH_DIR``, default ``<repo>/source/incoming/``),
returns its content formatted like a yfinance global-news string, then
archives the file so each upload is consumed exactly once.

Contract: registered against ``get_global_news`` in ``dataflows/interface.py``;
the existing News Analyst tool routes there unchanged — no agent/tool edits.
"""

import os

from .config import get_config
from .errors import NoMarketDataError

_SUPPORTED_EXTS = {".md", ".txt"}

# Housekeeping files that live in the ingest folder but are never research
# input (e.g. this folder's own README). Must not be consumed or archived.
_IGNORED_NAMES = {"readme.md", "readme.txt"}


def _newest_file(incoming: str):
    """Newest regular research file directly inside *incoming* (archive/ ignored)."""
    if not os.path.isdir(incoming):
        return None
    candidates = [
        os.path.join(incoming, name)
        for name in os.listdir(incoming)
        if os.path.isfile(os.path.join(incoming, name))
        and not name.startswith(".")
        and name.lower() not in _IGNORED_NAMES
        and os.path.splitext(name)[1].lower() in _SUPPORTED_EXTS
    ]
    return max(candidates, key=os.path.getmtime) if candidates else None


def get_external_research(
    curr_date: str,
    look_back_days: int | None = None,
    limit: int | None = None,
) -> str:
    """Return the newest uploaded research file as a news-style string.

    Mirrors ``get_global_news_yfinance``'s signature so the existing
    ``get_global_news`` tool can route here unchanged. Whole document is
    returned (a research brief is one item, not a list).

    Raises:
        NoMarketDataError: folder empty or only unsupported files — the
            router then falls through to the next configured vendor.
    """
    config = get_config()
    incoming = config["external_research_dir"]
    archive = os.path.join(incoming, "archive")

    newest = _newest_file(incoming)
    if newest is None:
        raise NoMarketDataError(
            "external_research",
            detail=f"no research files in {incoming}; drop a .md/.txt to add external research",
        )

    ext = os.path.splitext(newest)[1].lower()
    if ext not in _SUPPORTED_EXTS:
        raise NoMarketDataError(
            "external_research",
            detail=f"unsupported file type {ext!r} — convert PDFs to markdown before uploading",
        )

    with open(newest, encoding="utf-8", errors="replace") as fh:
        content = fh.read().strip()

    # Consume-once: move it out of the hot path so it is read exactly one run.
    os.makedirs(archive, exist_ok=True)
    os.rename(newest, os.path.join(archive, os.path.basename(newest)))

    # Strip Obsidian YAML frontmatter, if present.
    if content.startswith("---"):
        parts = content.split("---", 2)
        if len(parts) == 3:
            content = parts[2].strip()

    title = os.path.splitext(os.path.basename(newest))[0].replace("_", " ").replace("-", " ")
    return f"## External Research — {title} (source: user research):\n\n{content}\n"
