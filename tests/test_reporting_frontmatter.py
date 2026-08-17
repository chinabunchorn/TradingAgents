"""Obsidian adapter: frontmatter + wikilink decoration of complete reports, the
hub note (Trading Dashboard.md) linking all runs, and per-ticker hub notes
chaining each stock's history — the AI-OS write side (C2/C3 + graph fix)."""

from datetime import date as _today
from pathlib import Path

import pytest

from tradingagents.reporting import write_report_tree
from tradingagents.reporting_frontmatter import (
    decorate_complete_report,
    decorate_section_file,
    parse_report_meta,
    sync_hub_note,
    sync_ticker_hub,
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
def test_decorate_prepends_frontmatter_and_appends_single_line_wikilinks(tmp_path):
    p = _write_complete(tmp_path)
    decorate_complete_report(p, "AAPL", "2026-08-16")
    text = p.read_text(encoding="utf-8")

    assert text.startswith("---\n")
    fm = text.split("---", 2)[1]
    assert "ticker: AAPL" in fm
    assert "date: 2026-08-16" in fm
    # Graph fix: the note must resolve as [[2026-08-16 AAPL]] so the
    # Dashboard's Recent-runs links stop dangling.
    assert "aliases: 2026-08-16 AAPL" in fm
    assert "decision: Underweight" in fm
    assert "confidence: Medium" in fm
    # Wikilinks on exactly one line each, at the end: global index + ticker hub.
    lines = text.rstrip().splitlines()
    assert lines[-1] == "[[AAPL]]"
    assert lines[-2] == "[[Trading Dashboard]]"
    assert text.count("[[Trading Dashboard]]") == 1
    assert text.count("[[AAPL]]") == 1


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


@pytest.mark.unit
def test_decorate_section_file_prepends_frontmatter_and_links_run_and_hub(tmp_path):
    p = tmp_path / "market.md"
    p.write_text("MKT BODY\n", encoding="utf-8")
    decorate_section_file(p, "CRWD", "2026-08-17", "1_analysts/market")
    text = p.read_text(encoding="utf-8")

    assert text.startswith("---\n")
    fm = text.split("---", 2)[1]
    assert "ticker: CRWD" in fm
    assert "date: 2026-08-17" in fm
    assert "section: 1_analysts/market" in fm
    # Wikilinks on one line each: run note first, then ticker hub.
    lines = text.rstrip().splitlines()
    assert lines[-2] == "[[2026-08-17 CRWD]]"
    assert lines[-1] == "[[CRWD]]"


@pytest.mark.unit
def test_decorate_section_file_without_date_links_only_hub(tmp_path):
    # Old flat-tree files carry no trustworthy run-note date; only the hub link
    # is emitted so no dangling [[YYYY-MM-DD TICKER]] appears.
    p = tmp_path / "final_trade_decision.md"
    p.write_text("PM DECISION\n", encoding="utf-8")
    decorate_section_file(p, "CRWD", "", "final_trade_decision")
    text = p.read_text(encoding="utf-8")
    assert "[[CRWD]]" in text
    assert "[[2026-" not in text


@pytest.mark.unit
def test_decorate_section_file_is_idempotent(tmp_path):
    p = tmp_path / "bull.md"
    p.write_text("BULL BODY\n", encoding="utf-8")
    decorate_section_file(p, "CRWD", "2026-08-17", "2_research/bull")
    first = p.read_text(encoding="utf-8")
    decorate_section_file(p, "CRWD", "2026-08-17", "2_research/bull")
    assert p.read_text(encoding="utf-8") == first
    assert first.count("---") == 2


@pytest.mark.unit
def test_ticker_hub_created_and_chains_runs(tmp_path):
    hub = tmp_path / "CRWD.md"
    sync_ticker_hub(hub, "CRWD", "2026-08-16", "Underweight", "Medium")
    text = hub.read_text(encoding="utf-8")
    assert "# CRWD" in text and "## Runs" in text
    assert "- [[2026-08-16 CRWD]] — Underweight (Medium)" in text

    # A later run of the same stock appends; earlier entries never duplicate.
    sync_ticker_hub(hub, "CRWD", "2026-08-17", "Buy", "High")
    text2 = hub.read_text(encoding="utf-8")
    assert text2.count("- [[2026-08-16 CRWD]]") == 1
    assert "- [[2026-08-17 CRWD]] — Buy (High)" in text2


@pytest.mark.unit
def test_ticker_hub_wikilink_on_one_line(tmp_path):
    hub = tmp_path / "CRWD.md"
    sync_ticker_hub(hub, "CRWD", "2026-08-16", "Underweight", "Medium")
    for line in hub.read_text(encoding="utf-8").splitlines():
        if "[[2026-08-16 CRWD]]" in line:
            assert line.endswith("(Medium)")


@pytest.mark.unit
def test_write_report_tree_builds_resolvable_graph(tmp_path):
    """End-to-end graph wiring: the run note resolves as [[<date> <ticker>]],
    links both the global dashboard and its ticker hub, and the hub links
    back to the run — no dangling/phantom nodes."""
    state = {
        "market_report": "MKT",
        "news_report": "NEWS",
        "investment_debate_state": {"judge_decision": "RM PLAN"},
        "trader_investment_plan": "TRADE",
        "risk_debate_state": {"judge_decision": "PM DECISION"},
    }
    out = write_report_tree(state, "CRWD", tmp_path)

    text = out.read_text(encoding="utf-8")
    fm = text.split("---", 2)[1]
    assert f"aliases: {_today.today().isoformat()} CRWD" in fm
    assert "[[Trading Dashboard]]" in text
    assert "[[CRWD]]" in text

    hub = tmp_path.parent / "CRWD.md"  # sibling of Trading Dashboard.md
    hub_text = hub.read_text(encoding="utf-8")
    assert f"- [[{_today.today().isoformat()} CRWD]] — unknown (unknown)" in hub_text
