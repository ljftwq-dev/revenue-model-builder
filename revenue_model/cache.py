"""Disk cache for network adapters.

Avoids re-fetching the same remote data on every call (slow + rate-limit-prone —
recall SEC EDGAR flags automated traffic). Default location ``~/.cache/rmb/``
(per-platform standard); override with the ``RMB_CACHE_DIR`` environment variable
(e.g. ``RMB_CACHE_DIR=D:\\rmb_cache``).

JSON on disk (human-readable, inspectable). Core stays zero-dependency: this
module uses only stdlib, and importing it triggers no IO — only ``cache_get`` /
``cache_set`` touch the filesystem.
"""
import hashlib
import json
import os
import time
from pathlib import Path
from typing import Any, Tuple


def get_cache_dir() -> Path:
    """Resolve the cache directory. ``RMB_CACHE_DIR`` overrides the default
    ``~/.cache/rmb/``. Creates the directory if missing."""
    override = os.environ.get("RMB_CACHE_DIR")
    p = Path(override) if override else (Path.home() / ".cache" / "rmb")
    p.mkdir(parents=True, exist_ok=True)
    return p


def cache_key(adapter: str, *parts: Any) -> str:
    """Filesystem-safe cache key ``{adapter}_{parts}``. Long parts (e.g. URLs)
    are MD5-hashed to keep filenames short; separators are sanitized."""
    raw = "_".join(str(p) for p in parts)
    raw = raw.replace("/", "_").replace("\\", "_").replace(":", "_")
    if len(raw) > 60:
        raw = hashlib.md5(raw.encode()).hexdigest()[:16]
    return f"{adapter}_{raw}"


def cache_get(key: str, refresh: bool = False) -> Tuple[bool, Any]:
    """Return ``(hit, data)``. ``refresh=True`` or missing/invalid cache -> ``(False, None)``."""
    if refresh:
        return False, None
    p = get_cache_dir() / f"{key}.json"
    if not p.exists():
        return False, None
    try:
        return True, json.loads(p.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return False, None


def cache_set(key: str, data: Any) -> None:
    """Write ``data`` (JSON-serializable) to the cache atomically.

    Writes to a temp file then ``os.replace`` (atomic on both POSIX and
    Windows), so a concurrent reader never observes a half-written JSON even
    if the process crashes mid-write (M6: previously wrote in place, risking
    truncation / OSError under concurrent access from e.g. a Streamlit app).
    """
    d = get_cache_dir()
    p = d / f"{key}.json"
    tmp = d / f".{key}.json.tmp"
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(tmp, p)


# ---- TTL-aware cache (M4) -------------------------------------------------
# For slowly-changing but not immutable data (e.g. SEC company_tickers.json,
# which lags new IPOs / delistings / ticker renames). Stores ``{_data, _ts}``
# so callers can treat entries older than a max-age as stale and re-fetch.

def cache_set_timed(key: str, data: Any) -> None:
    """Store ``data`` with a write timestamp, for TTL-aware reads."""
    cache_set(key, {"_data": data, "_ts": time.time()})


def cache_get_timed(key: str, max_age_seconds: float, refresh: bool = False
                    ) -> Tuple[bool, Any]:
    """Return ``(hit, data)``; stale (older than ``max_age_seconds``) -> miss.

    Entries written by :func:`cache_set` (without timestamp) are treated as
    misses — only :func:`cache_set_timed` entries carry the timestamp this
    checks. ``refresh=True`` forces a miss.
    """
    if refresh:
        return False, None
    hit, wrapped = cache_get(key)
    if not hit or not isinstance(wrapped, dict) or "_ts" not in wrapped:
        return False, None
    if time.time() - wrapped["_ts"] > max_age_seconds:
        return False, None
    return True, wrapped.get("_data")
