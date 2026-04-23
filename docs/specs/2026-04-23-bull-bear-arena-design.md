# Bull vs Bear Arena — Design Spec

**Status:** approved 2026-04-23
**Origin:** `~/Downloads/BULL-BEAR-ARENA-PLAN.md` (React/Express/API variant), re-shaped for Streamlit + `claude -p` subprocess with an expanded 15-agent pipeline.

## Goal

A local Streamlit web app that runs a multi-agent debate on a user-supplied stock ticker and renders the full debate — each agent's argument, final verdict, and a quantitative price target — in the browser. Every agent call is a `claude -p` subprocess using the user's Claude Code subscription; no Anthropic API key anywhere.

## Non-goals

- No real trading, brokerage integration, or live quotes beyond what the researcher's WebSearch turns up.
- No cloud hosting. Runs locally (`streamlit run app.py`).
- No database. JSON files on disk.
- No per-user auth. Single-user local app.
- No React/Express rewrite.

## User flow

1. `streamlit run app.py` — browser opens at `localhost:8501`.
2. User types a ticker (e.g. `AAPL`) and optionally pastes notes (breaking news, earnings context, etc.).
3. User clicks **Debate**.
4. Progress bar + phase label update as each of 15 agents finishes (~4-7 min total).
5. Result panel renders: verdict badge, price-target strip, clash points, 12 agent cards (6 bull / 6 bear), researcher findings.
6. Debate JSON is saved to `debates/{TICKER}-{yyyymmdd-HHMM}.json`.
7. Past debates appear in the sidebar; clicking one reloads it into the main panel.

## Stack

- **Python 3.11+**
- **Streamlit** — single dependency for the UI
- **`claude -p` subprocess** — every agent call shells out to the Claude Code CLI. Subscription auth, no API key.
- **Local filesystem** — `debates/*.json` for persistence.

## Repo layout

```
bull-bear-arena/
├── README.md
├── requirements.txt         # streamlit
├── .gitignore               # __pycache__/, debates/, .venv/
├── app.py                   # Streamlit UI (entry point)
├── agents.py                # Pipeline orchestrator + subprocess wrapper
├── prompts.py               # All 15 system prompts
├── storage.py               # Save/load debate JSON
├── docs/
│   └── specs/
│       └── 2026-04-23-bull-bear-arena-design.md   # this file
└── debates/                 # runtime-created, gitignored
    └── AAPL-20260423-1432.json
```

## Agent pipeline (15 sequential calls per debate)

| # | Agent | Purpose | Tools | Output |
|---|---|---|---|---|
| 0 | 🔎 Researcher | Current price, P/E, revenue, margins, recent news | `WebSearch` | Plain prose paragraph; MUST include current share price as a numeric USD value at the top |
| 1 | 📊 Bull Fundamentals | Earnings, revenue, margins, balance sheet, ROE/ROIC | — | 2-3 prose paragraphs |
| 2 | 🚀 Bull Growth Catalysts | New products, TAM, innovation, AI adoption, international | — | 2-3 prose paragraphs |
| 3 | 🌍 Bull Macro Tailwinds | Industry trends, regulation, sector rotation, secular themes | — | 2-3 prose paragraphs |
| 4 | 🏰 Bull Moat & Pricing Power | Network effects, switching costs, brand, IP, scale | — | 2-3 prose paragraphs |
| 5 | 💎 Bull Capital Allocation | Buybacks, dividends, M&A discipline, insider buying | — | 2-3 prose paragraphs |
| 6 | 📈 Bull Technicals | Uptrend, breakouts, momentum, volume, moving averages | — | 2-3 prose paragraphs |
| 7 | ⚠️ Bear Risk Factors | Competitive threats, execution risk, regulatory/legal | — | 2-3 prose paragraphs |
| 8 | 💰 Bear Valuation | P/E vs peers, PEG, multiple compression, priced-in growth | — | 2-3 prose paragraphs |
| 9 | 🌪️ Bear Macro Headwinds | Geopolitics, rates, cyclicality, supply chain, currency | — | 2-3 prose paragraphs |
| 10 | 🎯 Bear Disruption & Obsolescence | Tech shifts, changing consumer habits, secular decline | — | 2-3 prose paragraphs |
| 11 | 🚩 Bear Accounting & Sentiment | Quality of earnings, insider selling, analyst downgrades, governance | — | 2-3 prose paragraphs |
| 12 | 📉 Bear Technicals | Downtrend, resistance, death cross, volume divergence | — | 2-3 prose paragraphs |
| 13 | ⚖️ Judge (Clash + Verdict) | 2-3 clash points + winner + conviction score + summary | `--json-schema` | Validated JSON |
| 14 | 🎯 Price Target Analyst | Bull/base/bear 12-month price targets with probability weighting | `--json-schema` | Validated JSON |

### Prompt inputs

- Researcher receives: ticker, today's date, user notes.
- Agents 1-12 receive: ticker, today's date, user notes, researcher's brief.
- Judge (13) receives: ticker, all 12 specialist arguments.
- Price Target Analyst (14) receives: researcher's brief (for current price), all 12 specialist arguments, judge verdict.

### Judge JSON schema (enforced via `--json-schema`)

```json
{
  "clashPoints": [
    {"topic": "string", "bull": "string", "bear": "string", "winner": "BULL|BEAR", "reasoning": "string"}
  ],
  "winner": "BULL|BEAR",
  "verdict": "integer 1-10",
  "summary": "string"
}
```

### Price Target JSON schema (enforced via `--json-schema`)

```json
{
  "currentPrice": "number (USD)",
  "bullCase":  {"price": "number", "probability": "number 0-1", "reasoning": "string"},
  "baseCase":  {"price": "number", "probability": "number 0-1", "reasoning": "string"},
  "bearCase":  {"price": "number", "probability": "number 0-1", "reasoning": "string"},
  "expectedValue": "number (USD)",
  "timeHorizon": "string (e.g., \"12 months\")",
  "methodology": "string (e.g., \"Forward P/E multiple + DCF cross-check\")"
}
```

Probabilities must sum to ~1.0. `expectedValue = bullCase.price * bullCase.probability + baseCase.price * baseCase.probability + bearCase.price * bearCase.probability`.

### Subprocess call shape

```python
subprocess.run([
    "claude", "-p",
    "--model", "sonnet",
    "--system-prompt", persona_text,
    "--output-format", "json",
    user_prompt,
], capture_output=True, text=True, check=True)
```

- Researcher adds `--allowedTools WebSearch`.
- Judge and Price Target add `--json-schema <schema>` for structured validation.
- `result.stdout` is itself JSON; the agent's text lives at `.result`. For structured-output agents, `.result` is a JSON string to parse further.

### Sequential-only execution

All 15 calls run serially. No parallelism — simplicity and subscription rate-limit friendliness. Expect ~4-7 min per debate end-to-end.

## UI layout

**Top of main panel**
- Title: `⚔️ Bull vs Bear Arena`
- Caption: one-liner subtitle.
- Form: ticker text input (required) + notes textarea (optional) + **Debate** button.

**Running state** (replaces form while debate is in progress)
- Progress bar 0/15 → 15/15
- Phase label: `🔎 Researching…` / `📊 Bull Fundamentals…` / `⚖️ Judging…` / `🎯 Building price target…`
- Expander showing the current agent's output as it completes

**Result state** (after debate completes or when loading from sidebar)

1. **Verdict banner** — big BULL or BEAR badge, conviction score 1-10, 2-3 sentence summary.
2. **Price target strip** — three `st.metric` widgets in a row:
   - Current: `$180.50`
   - 12mo Expected Target: `$192.50` (delta `+6.6%`)
   - Range: `$150 – $220`
   Below the metrics, a small horizontal bar visual (matplotlib or plain markdown) showing bear → current → base → bull.
3. **Clash points** — one `st.expander` per contradiction (bull side, bear side, winner, reasoning).
4. **Two columns** of agent analyses:
   - Left column (green accent): Fundamentals / Growth / Macro Tailwinds / Moat / Capital Allocation / Technicals — each an `st.expander`.
   - Right column (red accent): Risk / Valuation / Macro Headwinds / Disruption / Accounting & Sentiment / Technicals — each an `st.expander`.
5. **Price target methodology** — expander showing `methodology` + full reasoning for bull/base/bear cases.
6. **Researcher findings** — expander at bottom, collapsed by default.
7. **New debate** button — resets to form state.

**Sidebar**
- Header: "Past debates".
- List sorted newest-first: `AAPL · Apr 23 14:32 · BULL 8 · $192 (+6%)`.
- Click → reload into main panel.
- "Clear history" at bottom with confirmation.

## Data model (one file per debate)

```json
{
  "ticker": "AAPL",
  "timestamp": "2026-04-23T14:32:00",
  "notes": "",
  "researcher": "paragraph with current price etc.",
  "bull": {
    "fundamentals": "...",
    "growth": "...",
    "macro": "...",
    "moat": "...",
    "capital": "...",
    "technicals": "..."
  },
  "bear": {
    "risk": "...",
    "valuation": "...",
    "headwinds": "...",
    "disruption": "...",
    "accounting": "...",
    "technicals": "..."
  },
  "clash": {
    "clashPoints": [
      {"topic": "...", "bull": "...", "bear": "...", "winner": "BULL", "reasoning": "..."}
    ],
    "winner": "BULL",
    "verdict": 7,
    "summary": "..."
  },
  "priceTarget": {
    "currentPrice": 180.50,
    "bullCase":  {"price": 220, "probability": 0.30, "reasoning": "..."},
    "baseCase":  {"price": 195, "probability": 0.50, "reasoning": "..."},
    "bearCase":  {"price": 150, "probability": 0.20, "reasoning": "..."},
    "expectedValue": 192.50,
    "timeHorizon": "12 months",
    "methodology": "Forward P/E multiple + DCF cross-check"
  }
}
```

Filename: `{TICKER}-{yyyymmdd-HHMM}.json`. Multiple debates per ticker coexist. The `debates/` folder is gitignored.

## Error handling

| Failure | Behavior |
|---|---|
| `claude` subprocess non-zero exit | Red banner with stderr tail; `Retry` button re-runs the last agent only. |
| Researcher WebSearch fails / times out | Continue with `researcher = "n/a — WebSearch unavailable"`. Sub-agents run on world knowledge. Price Target agent still runs but `currentPrice` may be `null`; UI shows "price unavailable" and skips upside %. |
| Judge JSON parse fails (rare with `--json-schema`) | Show raw output; `Re-run judge` button only (keeps the 12 agent outputs). |
| Price Target JSON parse / probability-sum sanity fails | Show raw output; `Re-run price target` button. Renormalize probabilities if they sum to within 0.01 of 1.0 before failing. |
| Rate limit / 429 in stderr | Pause 30s, retry once. Second failure → bail with error. |
| `claude` binary not found at startup | Block the UI with "claude CLI not installed — run `which claude` to verify". |

## Model choice

- All specialist agents + researcher: `--model sonnet`.
- Judge and Price Target: `--model sonnet` to start. Bump either to `--model opus` later if outputs feel shallow.

## Out of scope (phase 2)

- Run-all-tickers batch mode
- Portfolio builder / allocation weights
- Side-by-side ticker comparison
- PDF/markdown export
- Historical charting of past verdicts for same ticker
- Alerts when a past debate's verdict would flip given new data

## Open questions

None at design time. Any runtime surprises get handled in implementation.

## Build order

1. Scaffold directory; `pip install -r requirements.txt`; smoke-test `claude -p "hi" --output-format json` from project root.
2. `prompts.py` — the 15 persona strings.
3. `agents.py` — subprocess wrapper, sequential pipeline, progress callback, JSON-schema invocations for judge & price target.
4. `storage.py` — save/load helpers.
5. `app.py` — Streamlit UI wiring everything (form, progress, result panels, sidebar).
6. Manual smoke test with AAPL + TSLA; tune prompts if outputs feel off.
