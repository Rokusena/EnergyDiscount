"""
Persistent deduplication — tracks which catalog URLs have been processed.

Entry format (new):
  { "seen_at": "2026-04-04T...", "expires": "2026-04-12" }

Old entries that are plain ISO strings are treated as never-expiring.
is_seen() returns False once today's date is past the stored expires date,
so expired catalogs are automatically re-processed on the next run.
"""
import json
import os
from datetime import date, datetime, timezone

SEEN_FILE = os.path.join(os.path.dirname(__file__), "seen_catalogs.json")


def _load() -> dict:
    if not os.path.exists(SEEN_FILE):
        return {}
    try:
        with open(SEEN_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return {}


def _save(data: dict) -> None:
    with open(SEEN_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def is_seen(url: str) -> bool:
    data = _load()
    if url not in data:
        return False

    entry = data[url]

    # Old format: plain ISO timestamp string — treat as never-expiring
    if isinstance(entry, str):
        return True

    # New format: dict with optional expires date
    expires = entry.get("expires")
    if expires:
        try:
            if date.today() > date.fromisoformat(expires):
                return False  # Catalog has expired — process it again
        except ValueError:
            pass  # Malformed date; be safe and treat as seen

    return True


def mark_seen(url: str, expires: str | None = None) -> None:
    """
    Mark a catalog URL as processed.
    expires: ISO date string "YYYY-MM-DD" — when this passes, is_seen() returns False.
    """
    data = _load()
    entry: dict = {"seen_at": datetime.now(timezone.utc).isoformat()}
    if expires and expires != "nežinoma":
        entry["expires"] = expires
    data[url] = entry
    _save(data)
