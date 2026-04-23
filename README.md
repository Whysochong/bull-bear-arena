# Bull vs Bear Arena

Local Streamlit app that runs a multi-agent stock debate using the Claude Code CLI (no API key).

You type a ticker, hit **Debate**, and fifteen sequential `claude -p` subprocess calls produce a research brief (with live WebSearch), twelve specialist arguments (6 bull, 6 bear), a judge's verdict with clash points and a 1-10 conviction score, and a quantitative price target with bull / base / bear scenarios. Results render as expandable panels and are saved as JSON in `debates/`.

## Requirements

- Python 3.11+
- `claude` CLI installed and authenticated (run `claude` once to sign in)

## Setup

```bash
pip install -r requirements.txt
streamlit run app.py
```

## Design

See [`docs/specs/2026-04-23-bull-bear-arena-design.md`](docs/specs/2026-04-23-bull-bear-arena-design.md).
