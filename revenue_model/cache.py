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
    """Write ``data`` (JSON-serializable) to the cache."""
    p = get_cache_dir() / f"{key}.json"
    p.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
