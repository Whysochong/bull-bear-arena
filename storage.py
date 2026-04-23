"""JSON-file persistence for debate results."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path


DEFAULT_DIR = Path(__file__).resolve().parent / "debates"


def _resolve_dir(base_dir: Path | None) -> Path:
    path = Path(base_dir) if base_dir else DEFAULT_DIR
    path.mkdir(parents=True, exist_ok=True)
    return path


def _filename_for(debate: dict) -> str:
    ticker = debate["ticker"].upper()
    ts = datetime.fromisoformat(debate["timestamp"])
    return f"{ticker}-{ts.strftime('%Y%m%d-%H%M')}.json"


def save_debate(debate: dict, *, base_dir: Path | None = None) -> Path:
    """Write debate dict as JSON, return the file path."""
    target_dir = _resolve_dir(base_dir)
    path = target_dir / _filename_for(debate)
    path.write_text(json.dumps(debate, indent=2))
    return path


def load_debate(path: Path) -> dict:
    """Load a single debate JSON file."""
    return json.loads(Path(path).read_text())


def list_debates(*, base_dir: Path | None = None) -> list[dict]:
    """Return debate summary entries sorted newest-first.

    Each entry: {path, ticker, timestamp, winner, verdict, expectedValue}.
    """
    target_dir = _resolve_dir(base_dir)
    entries: list[dict] = []
    for p in target_dir.glob("*.json"):
        try:
            d = json.loads(p.read_text())
        except (json.JSONDecodeError, OSError):
            continue
        entries.append({
            "path": p,
            "ticker": d.get("ticker", "?"),
            "timestamp": d.get("timestamp", ""),
            "winner": d.get("clash", {}).get("winner", "?"),
            "verdict": d.get("clash", {}).get("verdict", 0),
            "expectedValue": d.get("priceTarget", {}).get("expectedValue"),
        })
    entries.sort(key=lambda e: e["timestamp"], reverse=True)
    return entries


def clear_debates(*, base_dir: Path | None = None) -> int:
    """Delete every .json file in the debates directory. Returns count deleted."""
    target_dir = _resolve_dir(base_dir)
    count = 0
    for p in target_dir.glob("*.json"):
        p.unlink()
        count += 1
    return count
