"""Tests for qesa_adapter — QESA store read layer (SQLite fixture)."""

import os
import sqlite3

import pytest

from revenue_model.qesa_adapter import QesaStore, QesaStoreError

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


@pytest.fixture
def store(tmp_path):
    db = tmp_path / "qes.db"
    conn = sqlite3.connect(db)
    conn.executescript(SCHEMA)
    conn.execute("INSERT INTO series_registry VALUES "
                 "('PCOPPUSDM','LME Copper','commodity','$/mt','monthly','',1,'',0)")
    # three monthly observations, YoY filled for the last two
    rows = [
        ("PCOPPUSDM", "2026-05-01", 9000.0, 8800.0, 200.0, 5.0, "t"),
        ("PCOPPUSDM", "2026-06-01", 9500.0, 9000.0, 500.0, 9.0, "t"),
        ("PCOPPUSDM", "2026-07-01", 9900.0, 9500.0, 400.0, 12.0, "t"),
    ]
    conn.executemany("INSERT INTO observations VALUES (?,?,?,?,?,?,?)", rows)
    conn.execute("INSERT INTO events VALUES "
                 "('ev1','fred','macro_release','t','2026-07-01','title',"
                 "'PCOPPUSDM','commodity','up',3.2,'cost_shock_up','{}','h')")
    conn.commit()
    conn.close()
    s = QesaStore(path=str(db))
    yield s
    s.close()
    try:
        os.remove(str(db))
    except PermissionError:  # pragma: no cover - Windows file-lock races
        pass


class TestStoreLifecycle:
    def test_missing_db_raises(self, tmp_path):
        with pytest.raises(QesaStoreError):
            QesaStore(path=str(tmp_path / "nope.db"))

    def test_no_config_raises(self, monkeypatch):
        monkeypatch.delenv("QESA_DB", raising=False)
        with pytest.raises(QesaStoreError):
            QesaStore()

    def test_backend_is_sqlite(self, store):
        assert store.backend == "sqlite"

    def test_context_manager(self, store):
        with store:
            store.latest("PCOPPUSDM")


class TestReads:
    def test_series_history_full(self, store):
        obs = store.series_history("PCOPPUSDM")
        assert len(obs) == 3
        assert obs[0].date <= obs[-1].date
        assert obs[-1].yoy == 12.0

    def test_series_history_limit(self, store):
        obs = store.series_history("PCOPPUSDM", limit=2)
        assert len(obs) == 2
        assert obs[0].date == "2026-06-01"   # oldest-first after limit

    def test_latest(self, store):
        assert store.latest("PCOPPUSDM").value == 9900.0

    def test_latest_missing_series(self, store):
        with pytest.raises(QesaStoreError):
            store.latest("NOSUCH")

    def test_recent_shocks(self, store):
        evs = store.recent_shocks("PCOPPUSDM", days=3650)
        assert len(evs) == 1
        assert evs[0].tag == "cost_shock_up"
        assert evs[0].magnitude == 3.2

    def test_recent_shocks_magnitude_filter(self, store):
        assert store.recent_shocks("PCOPPUSDM", days=3650,
                                   min_abs_magnitude=5.0) == []

    def test_series_info(self, store):
        info = store.series_info("PCOPPUSDM")
        assert info["category"] == "commodity"
        assert info["unit"] == "$/mt"
