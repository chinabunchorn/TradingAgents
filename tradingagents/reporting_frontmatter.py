"""Obsidian report adapter — the AI-OS write side (Phases C2/C3).

Three small, dependency-free helpers that turn an already-generated
``complete_report.md`` into an Obsidian-ready note and keep a hub note
(``Trading Dashboard.md``) linking every run:

- ``parse_report_meta(body)``          → pull ``decision`` (Portfolio Manager
  ``**Rating**``) and ``confidence`` (``**Confidence:**``) out of the body.
- ``decorate_complete_report(path, …)``→ prepend YAML frontmatter
  (``ticker`` / ``date`` / ``aliases`` / ``decision`` / ``confidence``) and
  append one-line wikilinks to ``[[Trading Dashboard]]`` and the per-ticker
  hub ``[[<TICKER>]]``. Idempotent. The ``aliases: <date> <ticker>`` line
  makes the note resolve as ``[[YYYY-MM-DD TICKER]]`` — the exact name the
  Dashboard's ``## Recent runs`` lines link to (otherwise those links dangle
  as phantom nodes in Obsidian's graph).
- ``decorate_section_file(path, …)``→ prepend YAML frontmatter
  (``ticker`` / ``date`` / ``section``) and append one-line wikilinks to the
  per-ticker hub and (when a date is supplied) the dated run note. This is
  what stops every per-section note (``1_analysts/market.md``,
  ``2_research/bull.md``, ``5_portfolio/decision.md`` …) from stranding as an
  orphan node: the folder's files now cluster around the run instead of piling
  up disconnected. Idempotent.
- ``sync_hub_note(hub_path, …)``      → create/update the hub note's
  ``## Recent runs`` section with a ``[[YYYY-MM-DD TICKER]] — decision
  (confidence)`` line, never duplicating an entry.
- ``sync_ticker_hub(hub_path, …)``    → create/update a per-ticker hub note
  (``<TICKER>.md``) with a ``## Runs`` section chaining every dated run of
  that stock, so a ticker's history stays connected instead of piling up as
  isolated notes. Never duplicates an entry.

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
        # Lets Obsidian resolve the note as [[<date> <ticker>]] — the name
        # the Dashboard's Recent-runs lines already link to (graph fix: no
        # more dangling/phantom nodes), while the on-disk filename stays
        # complete_report.md so the watchdog and report-tree conventions
        # keep working untouched.
        f"aliases: {date} {ticker}\n"
        f"decision: {meta['decision']}\n"
        f"confidence: {meta['confidence']}\n"
        "---\n\n"
    )

    # Wikilinks on exactly one line each, appended at the end (Obsidian
    # rule): the global index plus this ticker's own hub note.
    decorated = (
        frontmatter
        + text.rstrip("\n")
        + "\n\n[[Trading Dashboard]]\n[["
        + ticker
        + "]]\n"
    )
    path.write_text(decorated, encoding="utf-8")
    return path


def decorate_section_file(path, ticker: str, date: str, section: str):
    """Prepend YAML frontmatter and append one-line wikilinks to a section note.

    Applies the same idea as :func:`decorate_complete_report` to the per-section
    files that sit inside a run's folder (``1_analysts/market.md``,
    ``2_research/bull.md``, ``3_trading/trader.md``, ``4_risk/aggressive.md``,
    ``5_portfolio/decision.md`` …). Without this every run scatters a dozen
    orphan notes into Obsidian's graph — nothing links to them and they link to
    nothing, so they accumulate as isolated nodes the more you research.

    The decorated note gains headline YAML (``ticker`` / ``date`` / ``section``)
    and, on exactly one line each (Obsidian rule), a `[[<date> <ticker>]]` link
    to its run note and a ``[[<TICKER>]]`` link to the per-ticker hub — so the
    whole folder clusters around the run. When ``date`` is empty (old flat-tree
    files whose date may not match the run-note alias), only the hub link is
    emitted to avoid dangling links. Idempotent.
    """
    path = Path(path)
    text = path.read_text(encoding="utf-8")

    if text.startswith("---\n"):
        return path

    frontmatter = (
        "---\n"
        f"ticker: {ticker}\n"
        f"date: {date}\n"
        f"section: {section}\n"
        "---\n\n"
    )

    links = [f"[[{ticker}]]"]
    if date:
        links.insert(0, f"[[{date} {ticker}]]")
    link_block = "\n".join(links) + "\n"

    decorated = frontmatter + text.rstrip("\n") + "\n\n" + link_block
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


def sync_ticker_hub(hub_path, ticker: str, date: str, decision: str, confidence: str):
    """Create/update a per-ticker hub note chaining every run of *ticker*.

    The hub (``<TICKER>.md`` at the reports root, next to
    ``Trading Dashboard.md``) gets a ``## Runs`` section with one line per
    dated run: ``- [[<date> <ticker>]] — decision (confidence)``. Reports
    link to it via the ``[[<TICKER>]]`` wikilink the decorator appends, so
    a stock's history forms a connected chain in Obsidian's graph instead
    of piling up as isolated notes. Entries are never duplicated.
    """
    hub_path = Path(hub_path)
    line = f"- [[{date} {ticker}]] {_EM_DASH} {decision} ({confidence})"

    if hub_path.exists():
        existing = hub_path.read_text(encoding="utf-8")
        if line in existing:
            return hub_path
        if "## Runs" in existing:
            new = existing.rstrip("\n") + "\n" + line + "\n"
        else:
            new = existing.rstrip("\n") + "\n\n## Runs\n\n" + line + "\n"
    else:
        new = f"# {ticker}\n\n## Runs\n\n" + line + "\n"

    hub_path.write_text(new, encoding="utf-8")
    return hub_path
