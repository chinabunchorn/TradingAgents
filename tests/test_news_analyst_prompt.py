"""Guard the news analyst prompt against tool-signature drift (#1116).

The prompt used to advertise ``get_news(query, ...)`` while the tool takes a
``ticker``, tricking the LLM into hallucinating free-text query calls.
"""
import inspect
from pathlib import Path

import pytest

import tradingagents.agents.analysts.news_analyst as na
import tradingagents.default_config as default_config
from tradingagents.agents.utils.news_data_tools import get_global_news, get_news
from tradingagents.dataflows.config import set_config


@pytest.mark.unit
def test_get_news_takes_ticker_not_query():
    arg_names = set(get_news.args.keys())
    assert "ticker" in arg_names
    assert "query" not in arg_names


@pytest.mark.unit
def test_news_prompt_matches_get_news_signature():
    src = inspect.getsource(na)
    assert "get_news(ticker, start_date, end_date)" in src
    assert "get_news(query" not in src


@pytest.fixture
def ingest(tmp_path: Path):
    """Point the external_research vendor at a temp ingest folder."""
    set_config({"external_research_dir": str(tmp_path)})
    yield tmp_path
    set_config({"external_research_dir": default_config.DEFAULT_CONFIG["external_research_dir"]})


@pytest.mark.unit
def test_global_news_tool_returns_pending_external_research(ingest, tmp_path):
    """Round-trip (A5): pending digest file → get_global_news tool → analyst input.

    The News Analyst has no file tools (R4): its only channel for the user's
    research is the get_global_news tool, which routes to the configured chain
    (external_research,yfinance). With a pending .md in the ingest folder the
    tool result must contain the digest body; get_news (ticker news) must stay
    on yfinance and never see the folder.
    """
    digest = tmp_path / "substack_compiled.md"
    digest.write_text(
        "## Budget highlights\n\nCapital expenditure guidance: 328M for FY27.",
        encoding="utf-8",
    )

    result = get_global_news.invoke({"curr_date": "2026-08-16"})

    assert "Capital expenditure guidance" in result
    assert "328M" in result
    assert "substack compiled" in result  # vendor title: filename prettified
    # Consume-once: the digested file moved out of the hot path.
    assert not digest.exists()
    assert (tmp_path / "archive" / "substack_compiled.md").exists()
