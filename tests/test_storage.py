import json
import os
from datetime import datetime

import storage


def _sample_debate(ticker: str = "AAPL", ts: str = "2026-04-23T14:32:00") -> dict:
    return {
        "ticker": ticker,
        "timestamp": ts,
        "notes": "",
        "researcher": "r",
        "bull": {"fundamentals": "f"},
        "bear": {"risk": "r"},
        "clash": {"winner": "BULL", "verdict": 7, "summary": "s", "clashPoints": []},
        "priceTarget": {
            "currentPrice": 100.0,
            "bullCase": {"price": 120, "probability": 0.3, "reasoning": "r"},
            "baseCase": {"price": 110, "probability": 0.5, "reasoning": "r"},
            "bearCase": {"price": 90,  "probability": 0.2, "reasoning": "r"},
            "expectedValue": 109.0,
            "timeHorizon": "12 months",
            "methodology": "m",
        },
    }


def test_save_and_load_roundtrip(tmp_path):
    debate = _sample_debate()
    path = storage.save_debate(debate, base_dir=tmp_path)
    assert path.exists()
    loaded = storage.load_debate(path)
    assert loaded == debate


def test_filename_shape(tmp_path):
    debate = _sample_debate(ticker="TSLA", ts="2026-04-23T14:32:00")
    path = storage.save_debate(debate, base_dir=tmp_path)
    assert path.name == "TSLA-20260423-1432.json"


def test_list_debates_returns_newest_first(tmp_path):
    storage.save_debate(_sample_debate("AAPL", "2026-04-20T10:00:00"), base_dir=tmp_path)
    storage.save_debate(_sample_debate("TSLA", "2026-04-23T14:32:00"), base_dir=tmp_path)
    storage.save_debate(_sample_debate("NVDA", "2026-04-22T09:00:00"), base_dir=tmp_path)

    entries = storage.list_debates(base_dir=tmp_path)
    tickers = [e["ticker"] for e in entries]
    assert tickers == ["TSLA", "NVDA", "AAPL"]
    assert all("path" in e and "timestamp" in e and "verdict" in e for e in entries)


def test_list_debates_includes_summary_fields(tmp_path):
    d = _sample_debate()
    storage.save_debate(d, base_dir=tmp_path)
    [entry] = storage.list_debates(base_dir=tmp_path)
    assert entry["winner"] == "BULL"
    assert entry["verdict"] == 7
    assert entry["expectedValue"] == 109.0


def test_clear_debates_removes_all_files(tmp_path):
    storage.save_debate(_sample_debate("A"), base_dir=tmp_path)
    storage.save_debate(_sample_debate("B", "2026-04-23T15:00:00"), base_dir=tmp_path)
    storage.clear_debates(base_dir=tmp_path)
    assert storage.list_debates(base_dir=tmp_path) == []


def test_list_debates_skips_non_json(tmp_path):
    (tmp_path / "note.txt").write_text("ignore me")
    storage.save_debate(_sample_debate(), base_dir=tmp_path)
    entries = storage.list_debates(base_dir=tmp_path)
    assert len(entries) == 1
