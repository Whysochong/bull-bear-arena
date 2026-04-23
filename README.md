# Bull vs Bear Arena

Local Streamlit app that runs a 15-agent stock debate using the Claude Code CLI.
No Anthropic API key — every agent call is a `claude -p` subprocess against your
Claude Code subscription.

Type a ticker, hit **Debate**, and in ~5–10 minutes you get:

- A researcher brief (live WebSearch: price, P/E, revenue, recent news)
- Twelve specialist arguments (6 bull, 6 bear covering fundamentals, growth,
  macro, moat, capital allocation, risk, valuation, disruption, accounting &
  sentiment, technicals)
- A judge's clash points + BULL/BEAR verdict + 1-10 conviction score
- A quantitative 12-month price target with bull / base / bear scenarios and
  a probability-weighted expected value

Results render in expandable panels. Each debate is saved as JSON under
`debates/` and listed in the sidebar for later viewing.

## Requirements

- Python 3.11+ (tested on 3.12)
- `claude` CLI 2.1+ installed and authenticated (run `claude` once
  interactively to sign in)

## Setup

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
streamlit run app.py
```

The app will open at http://localhost:8501.

## Project layout

```
app.py              Streamlit UI
agents.py           Pipeline orchestrator + claude -p subprocess wrapper
prompts.py          15 agent personas + 2 JSON schemas
storage.py          Save/load/list/clear debate JSON
tests/              pytest unit tests (no network, all mocked)
docs/
  specs/            Design doc
  plans/            Implementation plan
debates/            Saved debate results (gitignored)
```

## Running tests

```bash
./.venv/bin/python -m pytest tests/ -v
```

Tests mock subprocess calls, so they run in milliseconds and don't consume
your Claude subscription.

## Design

See [`docs/specs/2026-04-23-bull-bear-arena-design.md`](docs/specs/2026-04-23-bull-bear-arena-design.md)
for the full design and
[`docs/plans/2026-04-23-bull-bear-arena.md`](docs/plans/2026-04-23-bull-bear-arena.md)
for the implementation plan.
