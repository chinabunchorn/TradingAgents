"""Obsidian adapter: frontmatter + wikilink decoration of complete reports, and
the hub note (Trading Dashboard.md) linking runs — the AI-OS write side (C2/C3)."""

from pathlib import Path

import pytest

from tradingagents.reporting_frontmatter import (
    decorate_complete_report,
    parse_report_meta,
    sync_hub_note,
)

_BODY = (
    "# Trading Analysis Report: AAPL\n\n"
    "Generated: 2026-08-16 17:51:55\n\n"
    "## Sensitive Analyst Reports\n\n"
    "### Sentiment Analyst\n"
    "**Overall Sentiment:** Mixed (Score: 4.6/10)\n"
    "**Confidence:** Medium\n\n"
    "## V. Portfolio Manager Decision\n\n"
    "### Portfolio Manager\n"
    "**Rating**: Underweight\n\n"
    "**Executive Summary**: trim\n\n"
    "**Investment Thesis**: thesis\n"
)


def _write_complete(tmp_path: Path) -> Path:
    p = tmp_path / "complete_report.md"
    p.write_text(_BODY, encoding="utf-8")
    return p


@pytest.mark.unit
def test_parse_meta_extracts_rating_and_confidence():
    meta = parse_report_meta(_BODY)
    assert meta["decision"] == "Underweight"
    assert meta["confidence"] == "Medium"


@pytest.mark.unit
def test_parse_meta_defaults_when_absent_in_body():
    meta = parse_report_meta("# Trading Analysis Report: AAPL\n\nno rating here\n")
    assert meta["decision"] == "unknown"
    assert meta["confidence"] == "unknown"


@pytest.mark.unit
def test_decorate_prepends_frontmatter_and_appends_single_line_wikilink(tmp_path):
    p = _write_complete(tmp_path)
    decorate_complete_report(p, "AAPL", "2026-08-16")
    text = p.read_text(encoding="utf-8")

    assert text.startswith("---\n")
    fm = text.split("---", 2)[1]
    assert "ticker: AAPL" in fm
    assert "date: 2026-08-16" in fm
    assert "decision: Underweight" in fm
    assert "confidence: Medium" in fm
    # Wikilink on exactly one line, at the end.
    tail = text.rstrip().splitlines()[-1]
    assert tail == "[[Trading Dashboard]]"
    assert text.count("[[Trading Dashboard]]") == 1


@pytest.mark.unit
def test_decorate_is_idempotent(tmp_path):
    p = _write_complete(tmp_path)
    decorate_complete_report(p, "AAPL", "2026-08-16")
    first_text = p.read_text(encoding="utf-8")
    decorate_complete_report(p, "AAPL", "2026-08-16")
    assert p.read_text(encoding="utf-8") == first_text
    assert first_text.count("---") == 2  # only one frontmatter block


@pytest.mark.unit
def test_hub_note_created_and_appends_run_line(tmp_path):
    hub = tmp_path / "Trading Dashboard.md"
    sync_hub_note(hub, "AAPL", "2026-08-16", "Underweight", "Medium")
    text = hub.read_text(encoding="utf-8")
    assert "## Recent runs" in text
    assert "- [[2026-08-16 AAPL]] — Underweight (Medium)" in text

    # Second run appends, does not duplicate.
    sync_hub_note(hub, "MSFT", "2026-08-16", "Hold", "Low")
    text2 = hub.read_text(encoding="utf-8")
    assert text2.count("- [[2026-08-16 AAPL]]") == 1
    assert "- [[2026-08-16 MSFT]] — Hold (Low)" in text2


@pytest.mark.unit
def test_hub_note_renders_wikilink_on_one_line(tmp_path):
    hub = tmp_path / "Trading Dashboard.md"
    sync_hub_note(hub, "AAPL", "2026-08-16", "Underweight", "Medium")
    for line in hub.read_text(encoding="utf-8").splitlines():
        if "[[2026-08-16 AAPL]]" in line:
            assert line.endswith("(Medium)")
