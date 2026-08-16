# AGENTS.md — TradingAgents AI-OS Vault (`source/`)

> **Operating contract for the custom TradingAgents + Obsidian integration** ("AI OS").
> Brainstormed 2026-08-16 in the Hermes session that produced this vault.
> This file is the session handoff / source of truth: read it first each session, update it after each build step.

---

## 1. What this is

A custom fork of [TauricResearch/TradingAgents](https://github.com/TauricResearch/TradingAgents)
(`github.com/chinabunchorn/TradingAgents`, local: `~/TradingAgents`) wired into an
Obsidian vault as a personal AI OS:

- **Trading decisions land in the vault** as linked markdown notes (journal).
- **External research (Substack digests, budget reports, community research) enters the
  analysis** via the upload path — the custom function in §4.
- **Hermes (this agent) orchestrates**: schedules the pre-market run, drives Discord
  notifications, and lands every change as a reviewable PR on the fork.

## 2. Brainstorm decisions (locked 2026-08-16)

| #   | Decision               | Choice                                                       | Notes                                                                                                                                                                                   |
| --- | ---------------------- | ------------------------------------------------------------ | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| 1   | Obsidian compatibility | **Yes — thin adapter, no rewrite**                           | Reports are already markdown (`tradingagents/reporting.py` tree + `trading_memory.md` memory log). Only needs env-var re-pointing + YAML frontmatter + `[[wikilinks]]`.                 |
| 2   | Model assignment       | **DeepSeek V4 Pro 0813 = deep · V4 Flash 0731 = quick**      | Two-tier system built in (`deep_think_llm` / `quick_think_llm`). OpenRouter provider, custom model IDs. Mapping in §3.                                                                  |
| 3   | Notifications          | **Hermes cron → Discord, notification-only (watchdog mode)** | `no_agent=True` = script stdout delivered verbatim, no conversation. Pre-market schedule.                                                                                               |
| 4   | GitHub workflow        | **Yes — verified working**                                   | `gh` authenticated as `chinabunchorn` (scopes: `repo`, `workflow`). All changes land as PRs on the fork.                                                                                |
| 5   | Research sources       | **Upload path (chosen)**                                     | User uploads files manually into the ingest folder.                                                                                                                                     |
| 6   | PDF extraction         | **marker-pdf only when needed**                              | pymupdf (instant, zero deps) for text-layer PDFs; `marker-pdf` (~5 GB, needs install in vault `.venv`) for table-dense reports (budget reports!) and scans. Skill: `ocr-and-documents`. |

## 3. Model assignment — DeepSeek V4 Pro 0813 / V4 Flash 0731

Real token prices (user-confirmed):

| Model | Input / 1M | Output / 1M |
|---|---|---|
| DeepSeek V4 Pro 0813 | $0.435 | $0.87 |
| DeepSeek V4 Flash 0731 | $0.06846 | $0.1369 |

Env config (`.env` at repo root):

```
TRADINGAGENTS_LLM_PROVIDER=openrouter
TRADINGAGENTS_DEEP_THINK_LLM=deepseek/deepseek-v4-pro-0813
TRADINGAGENTS_QUICK_THINK_LLM=deepseek/deepseek-v4-flash-0731
```

Agent → tier mapping (`tradingagents/graph/setup.py:75–92`):

| Tier | Agents |
|---|---|
| **Pro 0813** (deep) | Research Manager (debate judge), Portfolio Manager (final approval). **← add Trader (recommended upgrade, +~$0.01/run)** |
| **Flash 0731** (quick) | Market/Technical, News, Fundamentals, Sentiment analysts · Bull & Bear researchers · Trader (until upgraded) · Aggressive/Neutral/Conservative risk debaters · Reflector + SignalProcessor (`trading_graph.py:137–138`) |

Cost model (measured judgment, verify with StatsCallbackHandler):

- Per ticker-run: **~$0.03–0.06** (150–250K in / 12–25K out on Flash; 30–60K in / 4–8K out on Pro)
- 5 tickers × daily pre-market ≈ **$3–6/month**; data APIs (yfinance/FRED/Polymarket) all free tier. Alpha Vantage free tier = 25 req/day (don't rely on it).
- Exact measurement: repo ships `StatsCallbackHandler` (`cli/stats_handler.py`) — use it on one real run before scaling.

## 4. THE CUSTOM FUNCTION — external research ingestion (upload path)

Core custom capability of this fork: **make the News Analyst read the user's own research
files** (Substack compilations, budget reports with tables, community digests) that land in
the vault.

### Contract

1. **User drops a file** into `<vault>/incoming/` (this vault's `incoming/` folder — create it if missing). Accepted: `.md` (direct), `.txt` (direct), `.pdf` (needs conversion, step 2).
2. **Convert PDF → markdown** (Hermes-side, NOT inside the repo): text-layer PDF → pymupdf (instant); table-dense/scanned PDF → `marker-pdf` via the `ocr-and-documents` skill (`extract_marker.py`), output into `<vault>/incoming/`. Rule: **tables must survive as markdown tables** — flattened text is unacceptable for budget reports.
3. **Repo hook: `external_research` vendor** (~60 lines, `tradingagents/dataflows/external_research.py`) — reads the **newest file by mtime** in `<vault>/incoming/` (archive/ ignored), returns its content in the same title/summary format the News Analyst already consumes, then archives the file to `<vault>/incoming/archive/` (consume-once).
4. **Registration** (exactly two places): `VENDOR_METHODS["get_global_news"]["external_research"]` and add `"external_research"` to `VENDOR_LIST` in `tradingagents/dataflows/interface.py:80–85`.
5. **Config chain** (default_config.py `tool_vendors`, tool-level precedence): `"get_global_news": "external_research,yfinance"` — user research is read whenever a file is pending; if the folder is empty the vendor raises `NoMarketDataError` and the router falls through to yfinance global news (identical to stock TradingAgents). `get_news` (per-ticker) keeps its `news_data` category default (`yfinance`) and never sees the ingest folder. *(Deviation from the original "union" wording: the router is ordered-fallback, not union — this chain expresses "user research first, mainstream as safety net, never one replacing the other" within the router's real semantics.)*
6. **Round-trip test**: a known digest file → vendor output → News Analyst prompt contains it. Keep the tests green (`pytest`).

### Why this shape

- Discord-fetching stays OUT of the repo — it's a future Hermes cron job that writes into `incoming/`, reusing the exact same hook (zero re-architecture).
- The repo stays lean: no marker/PyTorch deps in `pyproject.toml`.

## 5. Build status (updated 2026-08-16 after Phase A)

1. **`external_research` vendor (§4) → PR #1 `feature/external-research-vendor`** (open, CI pending); tests green (585 pass, ruff clean). ✅ built, in review
2. **Env config** (§3) → verify with one live run + StatsCallbackHandler → record true per-run cost in this file. *⚠️ Blocked: repo `.env` currently has NO `OPENROUTER_API_KEY` (removed 2026-08-16 to fix the Hermes-side 403 content-filter redaction; key lives in `~/.hermes/.env`). Re-add at run time only (`export OPENROUTER_API_KEY=…` or `.env`) — see plan Phase B.*
3. **Obsidian report adapter (write side)**: point `TRADINGAGENTS_RESULTS_DIR` → `<vault>/reports/`, `TRADINGAGENTS_MEMORY_LOG_PATH` → `<vault>/trading_memory.md`; prepend YAML frontmatter (`ticker`, `date`, `decision`, `confidence`) + wikilinks (one line each — Obsidian rule); hub note `[[Trading Dashboard]]` linking runs.
4. **marker-pdf install** in vault `.venv` (`pip install marker-pdf`, ~3–5 GB + ~2.5 GB model cache) — only when the first table-dense PDF arrives.
5. **Discord notification cron** (Hermes): pre-market, e.g. `30 20 * * 1-5` (NYSE 9:30 ET in Bangkok time). Watchdog style: read latest `complete_report.md` → print compact `📊 TICKER: action, confidence` line → delivered to Discord channel; empty stdout = silent. Notification only — no conversational bot.
6. **Optional later**: autonomous Discord fetch (same hook, cron fetcher), Trader → Pro upgrade, multi-ticker scaling (watch Alpha Vantage 25 req/day).

## 6. Architecture (one loop)

```text
Research file (manual upload) ──► source/incoming/
        │  (custom function §4: pymupdf | marker-pdf → md)
        ▼
external_research vendor ──► News Analyst ──► debate/trader/risk ──► Portfolio decision
        │                                                             │
cron (Hermes) ◄── pre-market run ◄────────────────────────────────────┘
        │
        ▼
Discord channel: compact notification only     Obsidian vault: reports/ + trading_memory.md
```

## 7. Grounding & standards (inherited from the house style)

- **Never fabricate numbers.** Prices/figures must trace to verified sources (OpenRouter pricing page, real run output). The user has rejected invented stats before.
- All code changes to the fork go through branches + PRs (`gh pr create`), CI + 160 tests as the safety net; `pytest` before/after each change.
- Obsidian notes: wikilinks on one line; YAML frontmatter for queryability.
- This file is the persistent project memory — update it (decision deltas, real costs, build status) at the end of every working session.