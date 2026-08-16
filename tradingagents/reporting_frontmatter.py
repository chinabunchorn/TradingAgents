"""Obsidian report adapter — the AI-OS write side (Phases C2/C3).

Three small, dependency-free helpers that turn an already-generated
``complete_report.md`` into an Obsidian-ready note and keep a hub note
(``Trading Dashboard.md``) linking every run:

- ``parse_report_meta(body)``          → pull ``decision`` (Portfolio Manager
  ``**Rating**``) and ``confidence`` (``**Confidence:**``) out of the body.
- ``decorate_complete_report(path, …)``→ prepend YAML frontmatter
  (``ticker`` / ``date`` / ``decision`` / ``confidence``) and append a
  one-line ``[[Trading Dashboard]]`` wikilink. Idempotent.
- ``sync_hub_note(hub_path, …)``      → create/update the hub note's
  ``## Recent runs`` section with a ``[[YYYY-MM-DD TICKER]] — decision
  (confidence)`` line, never duplicating an entry.

No agent/tool changes: the decoration is applied inside
``tradingagents/reporting.py`` (the single chokepoint every run's report
tree flows through), so the existing report writer stays untouched apart from
a thin call-out at the end.
"""

import re
from pathlib import Path

# Portfolio Manager's final rating is the canonical "decision"; the sentiment
# analyst is the one agent that emits a machine-readable confidence label.
# Tolerate both ``**Label**: value`` (colon outside the emphasis) and
# ``**Label:** value`` (colon inside the emphasis) — the reports use both.
_RATING_RE = re.compile(r"\*\*Rating:?\*\*\s*:?\s*(.+)")
_CONFIDENCE_RE = re.compile(r"\*\*Confidence:?\*\*\s*:?\s*(.+)")

_EM_DASH = "\u2014"


def _clean(value: str) -> str:
    """Strip whitespace and any surrounding emphasis markers from a label."""
    return value.strip().strip("*").strip()


def parse_report_meta(body: str) -> dict:
    """Extract ``decision`` and ``confidence`` from a rendered report body.

    Returns ``"unknown"`` for either key when the corresponding field is
    absent, so a sparse/minimal report still yields well-formed frontmatter.
    """
    decision = "unknown"
    confidence = "unknown"

    match = _RATING_RE.search(body)
    if match:
        decision = _clean(match.group(1))

    match = _CONFIDENCE_RE.search(body)
    if match:
        confidence = _clean(match.group(1))

    return {"decision": decision, "confidence": confidence}


def decorate_complete_report(path, ticker: str, date: str):
    """Prepend YAML frontmatter and append a one-line dashboard wikilink.

    Idempotent: if the file already starts with a frontmatter block, it is
    returned unchanged so re-running the writer never double-decorates.
    """
    path = Path(path)
    text = path.read_text(encoding="utf-8")

    if text.startswith("---\n"):
        return path

    meta = parse_report_meta(text)
    frontmatter = (
        "---\n"
        f"ticker: {ticker}\n"
        f"date: {date}\n"
        f"decision: {meta['decision']}\n"
        f"confidence: {meta['confidence']}\n"
        "---\n\n"
    )

    # Wikilink on exactly one line, appended at the end (Obsidian rule).
    decorated = frontmatter + text.rstrip("\n") + "\n\n[[Trading Dashboard]]\n"
    path.write_text(decorated, encoding="utf-8")
    return path


def sync_hub_note(hub_path, ticker: str, date: str, decision: str, confidence: str):
    """Append one run line to the hub note, creating it on first use.

    The line ``- [[<date> <ticker>]] — <decision> (<confidence>)`` is written
    under a ``## Recent runs`` section. Entries are never duplicated.
    """
    hub_path = Path(hub_path)
    line = f"- [[{date} {ticker}]] {_EM_DASH} {decision} ({confidence})"

    if hub_path.exists():
        existing = hub_path.read_text(encoding="utf-8")
        if line in existing:
            return hub_path
        if "## Recent runs" in existing:
            new = existing.rstrip("\n") + "\n" + line + "\n"
        else:
            new = existing.rstrip("\n") + "\n\n## Recent runs\n\n" + line + "\n"
    else:
        new = "# Trading Dashboard\n\n## Recent runs\n\n" + line + "\n"

    hub_path.write_text(new, encoding="utf-8")
    return hub_path
