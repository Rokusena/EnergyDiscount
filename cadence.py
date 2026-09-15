"""
Per-store catalog refresh cadence derived from run history in store_history.json.
Used as a secondary optimization signal — never overrides the real expiry gate in seen.py.
"""
import json
import logging
import os
from datetime import date, datetime

log = logging.getLogger(__name__)

HISTORY_FILE = os.path.join(os.path.dirname(__file__), "store_history.json")
_DAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]


def _load() -> dict:
    if not os.path.exists(HISTORY_FILE):
        return {}
    try:
        with open(HISTORY_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return {}


def _save(data: dict) -> None:
    with open(HISTORY_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def record_catalog(store_name: str, catalog_url: str, seen_at: str, expires: str | None) -> None:
    """Append a new catalog to this store's history. No-op if the URL is already recorded."""
    data = _load()
    entries = data.setdefault(store_name, [])
    if any(e["catalog_url"] == catalog_url for e in entries):
        return
    entries.append({"seen_at": seen_at, "expires": expires or "", "catalog_url": catalog_url})
    _save(data)


def get_cadence(store_name: str) -> dict | None:
    """
    Derive cadence from consecutive catalog appearances.
    Returns {avg_interval_days, weekday, weekday_num, sample_size} or None if < 2 entries.
    """
    entries = _load().get(store_name, [])
    if len(entries) < 2:
        return None

    sorted_entries = sorted(entries, key=lambda e: e["seen_at"])
    weekdays = [datetime.fromisoformat(e["seen_at"]).date().weekday() for e in sorted_entries]
    intervals = []
    for i in range(1, len(sorted_entries)):
        d1 = datetime.fromisoformat(sorted_entries[i - 1]["seen_at"]).date()
        d2 = datetime.fromisoformat(sorted_entries[i]["seen_at"]).date()
        delta = (d2 - d1).days
        if delta > 0:
            intervals.append(delta)

    if not intervals:
        return None

    avg = sum(intervals) / len(intervals)
    dominant_wd = max(set(weekdays), key=weekdays.count)
    return {
        "avg_interval_days": round(avg),
        "weekday":           _DAYS[dominant_wd],
        "weekday_num":       dominant_wd,
        "sample_size":       len(entries),
    }


def check_anomaly(store_name: str, catalog_url: str, today: date) -> None:
    """Warn when a new catalog lands on an unexpected weekday (may indicate site layout change)."""
    cadence = get_cadence(store_name)
    if cadence is None or cadence["sample_size"] < 3:
        return

    today_wd = today.weekday()
    expected_wd = cadence["weekday_num"]
    diff = min(abs(today_wd - expected_wd), 7 - abs(today_wd - expected_wd))
    if diff > 1:
        log.warning(
            "[cadence] %s: new catalog on %s but expected around %s — possible layout change. url=%s",
            store_name, _DAYS[today_wd], cadence["weekday"], catalog_url,
        )
