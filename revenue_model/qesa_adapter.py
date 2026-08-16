"""QESA adapter — read the Quant Event Signal Aggregator store from rmb.

Bridges the QESA event database (upstream macro/commodity/FX series built with
``qes_fetch.py``) into driver-based revenue models. This is the data layer of
the *event -> driver revision -> re-run* loop: Direction-3 concluded that news
is a wave detector whose value is triggering driver revisions — never direct
event->revenue regressions — and this adapter supplies the quantified upstream
signals that make those revisions rule-based instead of hand-waved.

Backends (mirroring QESA's own dual-backend design):
- SQLite (default, stdlib only) — path via ``path=`` or env ``QESA_DB``.
- MySQL (optional) — dsn dict like ``secrets_loader.get_mysql_config()``,
  requires ``pymysql`` (extra: ``pip install revenue-model-builder[qesa]``).

Tables expected (created by QESA ``qes_fetch.init_db``):
- ``observations(series_id, obs_date, value, prev_value, change, yoy, ingest_time)``
- ``events(event_id, source, event_type, event_time, ref_date, title,
          series_id, category, direction, magnitude, tag, payload, content_hash)``
- ``series_registry(series_id, name, category, unit, frequency, ...)``

All pure-read: this adapter never writes.
"""

import os
import sqlite3
from typing import Any, Dict, List, Optional, Sequence

__all__ = ["QesaStore", "QesaStoreError", "Observation", "Event"]


class QesaStoreError(RuntimeError):
    """Raised when the QESA store is missing or unreadable."""


class Observation:
    """One data point of an upstream series."""

    __slots__ = ("series_id", "date", "value", "change", "yoy")

    def __init__(self, series_id: str, date: str, value: float,
                 change: Optional[float], yoy: Optional[float]):
        self.series_id = series_id
        self.date = date            # ISO date string, e.g. '2026-08-01'
        self.value = value
        self.change = change        # period-over-period delta (None for first)
        self.yoy = yoy              # percent YoY (None when not computable)

    def __repr__(self) -> str:  # pragma: no cover - debug aid
        return (f"Observation({self.series_id}, {self.date}, {self.value}, "
                f"change={self.change}, yoy={self.yoy})")


class Event:
    """One tagged event from the QESA event stream."""

    __slots__ = ("event_id", "series_id", "ref_date", "category", "direction",
                 "magnitude", "tag", "title")

    def __init__(self, event_id: str, series_id: str, ref_date: str,
                 category: str, direction: str, magnitude: Optional[float],
                 tag: str, title: str):
        self.event_id = event_id
        self.series_id = series_id
        self.ref_date = ref_date
        self.category = category
        self.direction = direction
        self.magnitude = magnitude
        self.tag = tag
        self.title = title

    def __repr__(self) -> str:  # pragma: no cover - debug aid
        return f"Event({self.tag}, {self.series_id}, {self.ref_date})"


class QesaStore:
    """Read-only accessor for a QESA database (SQLite or MySQL)."""

    def __init__(self, path: Optional[str] = None,
                 dsn: Optional[Dict[str, Any]] = None):
        self._dsn = dsn
        self._path = path or os.environ.get("QESA_DB")
        if dsn is None and not self._path:
            raise QesaStoreError(
                "QESA store not configured: pass path=... (SQLite) or "
                "dsn=... (MySQL), or set QESA_DB=/path/to/qes.db")
        if dsn is not None:
            try:
                import pymysql
                import pymysql.cursors
            except ImportError as exc:  # pragma: no cover - env dependent
                raise QesaStoreError(
                    "MySQL backend needs pymysql: "
                    "pip install 'revenue-model-builder[qesa]'") from exc
            self._conn = pymysql.connect(
                cursorclass=pymysql.cursors.DictCursor, **dsn)
            self._backend = "mysql"
        else:
            if not os.path.exists(self._path):
                raise QesaStoreError(f"QESA sqlite db not found: {self._path}")
            self._conn = sqlite3.connect(self._path)  # type: ignore[assignment]
            self._conn.row_factory = sqlite3.Row
            self._backend = "sqlite"

    # -- internals ---------------------------------------------------------
    def _q(self, sql: str) -> str:
        """QESA writes SQL with ? placeholders; MySQL wants %s."""
        return sql.replace("?", "%s") if self._backend == "mysql" else sql

    def _rows(self, sql: str, args: Sequence[Any] = ()) -> List[Dict[str, Any]]:
        cur = self._conn.cursor()
        cur.execute(self._q(sql), tuple(args))
        return [dict(r) for r in cur.fetchall()]

    # -- public API ---------------------------------------------------------
    @property
    def backend(self) -> str:
        return self._backend

    def series_history(self, series_id: str, limit: Optional[int] = None
                       ) -> List[Observation]:
        """Observations oldest-first (optionally last ``limit`` points)."""
        if limit:
            rows = self._rows(
                "SELECT * FROM (SELECT series_id, obs_date, value, `change`, "
                "yoy FROM observations WHERE series_id=? "
                "ORDER BY obs_date DESC LIMIT ?) t ORDER BY obs_date",
                (series_id, limit))
        else:
            rows = self._rows(
                "SELECT series_id, obs_date, value, `change` AS `change`, yoy "
                "FROM observations WHERE series_id=? ORDER BY obs_date",
                (series_id,))
        return [Observation(r["series_id"], r["obs_date"], r["value"],
                            r.get("change"), r.get("yoy")) for r in rows]

    def latest(self, series_id: str) -> Observation:
        obs = self.series_history(series_id, limit=1)
        if not obs:
            raise QesaStoreError(f"no observations for series {series_id!r}")
        return obs[0]

    def recent_shocks(self, series_id: str, days: int = 180,
                      min_abs_magnitude: float = 0.0) -> List[Event]:
        """Events for ``series_id`` within the last ``days`` days (newest last).

        ``min_abs_magnitude`` filters on |event.magnitude| (units differ per
        category: pct-change for commodity/fx, pp YoY for ppi/inflation).
        """
        if self._backend == "mysql":
            rows = self._rows(
                "SELECT event_id, series_id, ref_date, category, direction, "
                "magnitude, tag, title FROM events WHERE series_id=? "
                f"AND ref_date >= DATE_SUB(CURDATE(), INTERVAL {int(days)} DAY) "
                "ORDER BY ref_date", (series_id,))
        else:
            rows = self._rows(
                "SELECT event_id, series_id, ref_date, category, direction, "
                "magnitude, tag, title FROM events WHERE series_id=? "
                "AND ref_date >= date('now', ?) ORDER BY ref_date",
                (series_id, f"-{int(days)} days"))
        out = []
        for r in rows:
            mag = r.get("magnitude")
            if min_abs_magnitude and (mag is None or
                                      abs(mag) < min_abs_magnitude):
                continue
            out.append(Event(r["event_id"], r["series_id"], r["ref_date"],
                             r["category"], r["direction"], mag,
                             r["tag"], r["title"]))
        return out

    def series_info(self, series_id: str) -> Dict[str, Any]:
        rows = self._rows(
            "SELECT series_id, name, category, unit, frequency FROM "
            "series_registry WHERE series_id=?", (series_id,))
        if not rows:
            raise QesaStoreError(f"series {series_id!r} not in registry")
        return rows[0]

    def close(self) -> None:
        self._conn.close()

    def __enter__(self) -> "QesaStore":
        return self

    def __exit__(self, *exc) -> None:
        self.close()
