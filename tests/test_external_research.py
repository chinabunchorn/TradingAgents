"""Tests for the external_research vendor (AI-OS upload path)."""

import copy
import os
from pathlib import Path
from unittest import mock

import pytest

import tradingagents.dataflows.config as config_module
import tradingagents.default_config as default_config
from tradingagents.dataflows import interface
from tradingagents.dataflows.config import set_config
from tradingagents.dataflows.errors import NoMarketDataError
from tradingagents.dataflows.external_research import get_external_research


@pytest.fixture
def ingest(tmp_path: Path):
    """Temp ingest folder with a fresh copy of the default config."""
    set_config({"external_research_dir": str(tmp_path)})
    yield tmp_path
    set_config({"external_research_dir": default_config.DEFAULT_CONFIG["external_research_dir"]})


def _write(ingest: Path, name: str, content: str, mtime: float = 1_700_000_000):
    p = ingest / name
    p.write_text(content, encoding="utf-8")
    os.utime(p, (mtime, mtime))
    return p


def test_returns_newest_md_file(ingest: Path):
    older = _write(ingest, "older.md", "old digest body", mtime=1_000)
    newer = _write(ingest, "substack_compiled.md", "new digest body", mtime=2_000)
    result = get_external_research("2026-08-16", None, None)
    assert "new digest body" in result
    assert "substack compiled" in result  # filename prettified: _ → space
    assert "old digest body" not in result
    # Consume-once: the newest file is archived...
    assert not newer.exists()
    assert (ingest / "archive" / "substack_compiled.md").exists()
    # ...and the older one is untouched.
    assert older.exists()


def test_empty_folder_raises_no_market_data(ingest: Path):
    with pytest.raises(NoMarketDataError):
        get_external_research("2026-08-16", None, None)


def test_unsupported_pdf_is_not_consumed(ingest: Path):
    _write(ingest, "budget.pdf", "%PDF-1.4 fake", mtime=1_000)
    with pytest.raises(NoMarketDataError, match="unsupported"):
        get_external_research("2026-08-16", None, None)
    assert (ingest / "budget.pdf").exists()  # left in place for conversion


def test_strips_yaml_frontmatter(ingest: Path):
    _write(ingest, "note.md",
           "---\nticker: AAPL\ntype: digest\n---\nreal content here", mtime=1_000)
    result = get_external_research("2026-08-16", None, None)
    assert "real content here" in result
    assert "type: digest" not in result


def test_unsupported_extension_types_are_ignored_over_md(ingest: Path):
    # A .txt and a .md compete by mtime; the newest supported file wins.
    md = _write(ingest, "note.md", "from markdown", mtime=2_000)
    _write(ingest, "scrape.txt", "from text", mtime=1_000)
    result = get_external_research("2026-08-16", None, None)
    assert "from markdown" in result
    assert not md.exists()  # consumed
    assert (ingest / "archive" / "note.md").exists()


def test_folder_readme_is_never_consumed(ingest: Path):
    # The ingest folder's own README.md must not be treated as research input
    # (regression: previously the newest-file picker consumed README.md and
    # archived it, breaking the folder contract after the first run).
    _write(ingest, "README.md", "the folder contract", mtime=9_999_999)
    with pytest.raises(NoMarketDataError):
        get_external_research("2026-08-16", None, None)
    assert (ingest / "README.md").exists()  # left in place
    assert not (ingest / "archive" / "README.md").exists()


def test_registered_in_interface():
    assert "external_research" in interface.VENDOR_LIST
    assert interface.VENDOR_METHODS["get_global_news"]["external_research"] is get_external_research


def test_routing_falls_through_to_yfinance_when_empty(ingest: Path):
    # Tool-level chain "external_research,yfinance": with an empty folder the
    # vendor raises NoMarketDataError, so the router must fall through to the
    # next configured vendor (yfinance) — same behavior as stock TradingAgents.
    yfinance_mock = mock.Mock(return_value="YFINANCE_GLOBAL_NEWS")
    chain = {"external_research": get_external_research, "yfinance": yfinance_mock}

    prev_tool_vendors = config_module._config.get("tool_vendors", {})
    try:
        set_config({"tool_vendors": {"get_global_news": "external_research,yfinance"}})
        with mock.patch.dict(
            interface.VENDOR_METHODS, {"get_global_news": chain}, clear=False
        ):
            result = interface.route_to_vendor("get_global_news", "2026-08-16", 7, 20)
    finally:
        config_module._config["tool_vendors"] = copy.deepcopy(prev_tool_vendors)

    assert result == "YFINANCE_GLOBAL_NEWS"
    yfinance_mock.assert_called_once_with("2026-08-16", 7, 20)
