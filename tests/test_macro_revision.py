"""Tests for macro_revision — the event -> driver revision -> re-run loop."""

import sqlite3

import pytest

from revenue_model import (Driver, BASE, SHARE, PRICE, LEVEL_B,
                           MacroBinding, suggest_revisions, apply_revision)
from revenue_model.qesa_adapter import QesaStore

SCHEMA = """
CREATE TABLE series_registry (
    series_id TEXT PRIMARY KEY, name TEXT, category TEXT, unit TEXT,
    frequency TEXT, impact_note TEXT, active INTEGER, added_at TEXT,
    invert INTEGER DEFAULT 0);
CREATE TABLE observations (
    series_id TEXT, obs_date TEXT, value REAL, prev_value REAL,
    `change` REAL, yoy REAL, ingest_time TEXT,
    PRIMARY KEY (series_id, obs_date));
CREATE TABLE events (
    event_id TEXT PRIMARY KEY, source TEXT, event_type TEXT, event_time TEXT,
    ref_date TEXT, title TEXT, series_id TEXT, category TEXT, direction TEXT,
    magnitude REAL, tag TEXT, payload TEXT, content_hash TEXT);
"""

BINDINGS = [
    MacroBinding(series_id="PCOPPUSDM", label="LME铜", channel="cost",
                 target="单台设备价值", elasticity=0.08, lag_quarters=3,
                 note="QESA面板: 材料×铜 β=1.36 (营收口径)"),
    MacroBinding(series_id="DEXCHUS", label="人民币汇率", channel="fx",
                 target="单台设备价值", elasticity=0.30, lag_quarters=1),
]


def make_store(tmp_path, series):
    db = tmp_path / "qes.db"
    conn = sqlite3.connect(db)
    conn.executescript(SCHEMA)
    for sid, rows in series.items():
        for r in rows:
            conn.execute("INSERT INTO observations VALUES (?,?,?,?,?,?,?)",
                         (sid, *r))
    conn.commit()
    conn.close()
    return QesaStore(path=str(db))


class TestMacroBinding:
    def test_bad_channel_rejected(self):
        with pytest.raises(ValueError):
            MacroBinding("X", "x", "weather", "y", 1.0, 1)

    def test_negative_lag_rejected(self):
        with pytest.raises(ValueError):
            MacroBinding("X", "x", "cost", "y", 1.0, -1)


class TestSuggest:
    def test_triggers_on_yoy_jump(self, tmp_path):
        # yoy moves 8.0 -> 11.5 (delta 3.5pp) -> triggers at min 1pp
        store = make_store(tmp_path, {"PCOPPUSDM": [
            ("2026-06-01", 9500.0, 9000.0, 500.0, 8.0, "t"),
            ("2026-07-01", 9900.0, 9500.0, 400.0, 11.5, "t")]})
        sug = suggest_revisions(BINDINGS, store, min_shock_pp=1.0)
        assert len(sug) == 1
        s = sug[0]
        assert s.binding.series_id == "PCOPPUSDM"
        assert s.shock_delta_pp == pytest.approx(3.5)
        assert s.implied_pp == pytest.approx(0.08 * 3.5)
        assert s.lands_quarter.startswith("202")

    def test_no_trigger_below_threshold(self, tmp_path):
        store = make_store(tmp_path, {"PCOPPUSDM": [
            ("2026-06-01", 9500.0, 9000.0, 500.0, 8.0, "t"),
            ("2026-07-01", 9600.0, 9500.0, 100.0, 8.4, "t")]})
        assert suggest_revisions(BINDINGS, store, min_shock_pp=1.0) == []

    def test_missing_series_skipped(self, tmp_path):
        store = make_store(tmp_path, {"OTHER": [
            ("2026-06-01", 1.0, 1.0, 0.0, 2.0, "t")]})
        assert suggest_revisions(BINDINGS, store) == []

    def test_summary_contains_evidence(self, tmp_path):
        store = make_store(tmp_path, {"DEXCHUS": [
            ("2026-06-01", 7.10, 7.00, 0.10, 1.0, "t"),
            ("2026-07-01", 7.30, 7.10, 0.20, 4.0, "t")]})
        sug = suggest_revisions(BINDINGS, store)
        assert len(sug) == 1
        text = sug[0].summary()
        assert "人民币汇率" in text and "滞后1季" in text


class TestApply:
    def _sug(self, tmp_path):
        store = make_store(tmp_path, {"PCOPPUSDM": [
            ("2026-06-01", 9500.0, 9000.0, 500.0, 8.0, "t"),
            ("2026-07-01", 9900.0, 9500.0, 400.0, 12.0, "t")]})
        return suggest_revisions(BINDINGS, store)[0]

    def test_price_driver_multiplicative(self, tmp_path):
        sug = self._sug(tmp_path)   # implied 0.08*4 = 0.32pp
        d = Driver("单台设备价值", PRICE, {2025: 1000.0}, level=LEVEL_B,
                   unit="元", source="implied")
        d2 = apply_revision(d, sug, years=[2026])
        assert d2.values[2026] == pytest.approx(1000.0 * 1.0032)
        assert d2.level == "C"
        assert "macro-signal" in d2.source and "β" in d2.source
        # original untouched
        assert d.values == {2025: 1000.0}

    def test_share_driver_absolute_pp(self, tmp_path):
        store = make_store(tmp_path, {"PCOPPUSDM": [
            ("2026-06-01", 9500.0, 9000.0, 500.0, 8.0, "t"),
            ("2026-07-01", 9900.0, 9500.0, 400.0, 12.0, "t")]})
        sug = suggest_revisions(BINDINGS, store)[0]
        sug.binding = MacroBinding("PCOPPUSDM", "LME铜", "demand",
                                   "立讯苹果供应链份额", 0.08, 3)
        d = Driver("立讯苹果供应链份额", SHARE, {2025: 0.33}, level=LEVEL_B,
                   unit="fraction", source="est")
        d2 = apply_revision(d, sug, years=[2026, 2027])
        # 0.32pp spread over window=1yr: +0.0032 by 2026, same cumulative 2027
        assert d2.values[2026] == pytest.approx(0.33 + 0.0032)
        assert d2.values[2027] == pytest.approx(0.33 + 0.0032)

    def test_window_spread(self, tmp_path):
        sug = self._sug(tmp_path)
        sug.binding = MacroBinding(sug.binding.series_id, sug.binding.label,
                                   "cost", "单台设备价值", 0.08, 3,
                                   window_years=2)
        d = Driver("单台设备价值", PRICE, {2025: 1000.0})
        d2 = apply_revision(d, sug, years=[2026, 2027])
        assert d2.values[2026] == pytest.approx(1000.0 * 1.0016)
        assert d2.values[2027] == pytest.approx(1000.0 * 1.0032)

    def test_target_mismatch_raises(self, tmp_path):
        sug = self._sug(tmp_path)
        d = Driver("别的driver", BASE, {2025: 100.0})
        with pytest.raises(ValueError):
            apply_revision(d, sug, years=[2026])
