"""
Manages deals.json — the structured public data feed consumed by the portfolio site.

Schema matches what the companion Next.js site expects at:
  https://raw.githubusercontent.com/Rokusena/EnergyDiscount/main/deals.json
"""
import json
import logging
import os
import re
from datetime import date, datetime, timezone

log = logging.getLogger(__name__)

DEALS_FILE = os.path.join(os.path.dirname(__file__), "deals.json")


def _parse_float(s) -> float | None:
    if not s:
        return None
    clean = re.sub(r"[^\d,.]", "", str(s)).replace(",", ".")
    try:
        return float(clean)
    except ValueError:
        return None


def _parse_volume_liters(product: str) -> float | None:
    # Multipacks first: "4 x 0.5l" is 2L, not 0.5L. Matching the single-unit
    # patterns first would silently price a 4-pack as one can.
    # Note "2 rūšių" (2 varieties) is not a multiplier, so an explicit x is required.
    m = re.search(r"(\d+)\s*[x×]\s*(\d+(?:[.,]\d+)?)\s*(ml|l)\b", product, re.IGNORECASE)
    if m:
        count  = int(m.group(1))
        volume = float(m.group(2).replace(",", "."))
        if m.group(3).lower() == "ml":
            volume /= 1000
        total = count * volume
        if 0 < total < 20:
            return round(total, 4)

    # millilitres: "330ml", "355 ml", "500ML"
    m = re.search(r"(\d+(?:[.,]\d+)?)\s*ml", product, re.IGNORECASE)
    if m:
        return round(float(m.group(1).replace(",", ".")) / 1000, 4)
    # litres: "0.5l", "0.553 l", "1.5L" — guard against misparses > 10 L
    m = re.search(r"(\d+(?:[.,]\d+)?)\s*l\b", product, re.IGNORECASE)
    if m:
        val = float(m.group(1).replace(",", "."))
        if val < 10:
            return round(val, 4)
    return None


def _load() -> dict:
    if not os.path.exists(DEALS_FILE):
        return {"generated_at": "", "deals": []}
    try:
        with open(DEALS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return {"generated_at": "", "deals": []}


def _save(data: dict) -> None:
    with open(DEALS_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _build_entry(store_name: str, deal: dict, valid_until: str,
                 scraped_at: str, catalog_url: str) -> dict:
    product   = deal.get("product", "")
    price     = _parse_float(deal.get("sale_price"))
    old_price = _parse_float(deal.get("regular_price"))

    entry: dict = {
        "store":       store_name,
        "product":     product,
        "price":       price,
        "old_price":   old_price,
        "valid_until": valid_until,
        "scraped_at":  scraped_at,
        "catalog_url": catalog_url,
    }

    if price and old_price and old_price > 0 and price < old_price:
        entry["discount_percent"] = round((1 - price / old_price) * 100)
    else:
        entry["discount_percent"] = None

    vol = _parse_volume_liters(product)
    entry["price_per_liter"] = round(price / vol, 2) if (price and vol and vol > 0) else None

    return entry


def update_deals(store_name: str, new_deals: list[dict], valid_until: str,
                 scraped_at: str, catalog_url: str) -> None:
    """
    Replace all entries for store_name with new_deals.
    Entries from other stores whose valid_until has passed are pruned at the same time.
    Rewrites deals.json completely.
    """
    today_str = date.today().isoformat()
    data = _load()

    kept = [
        d for d in data.get("deals", [])
        if d.get("store") != store_name and d.get("valid_until", "9999") >= today_str
    ]
    # A deal with no extractable price isn't displayable — GPT-4o sometimes
    # returns a product line (e.g. an assortment ad) without a readable price.
    new_entries = [
        _build_entry(store_name, d, valid_until, scraped_at, catalog_url)
        for d in new_deals
        if _parse_float(d.get("sale_price")) is not None
    ]

    data["generated_at"] = _now_iso()
    data["deals"] = kept + new_entries
    _save(data)
    log.info("[deals] %s: %d entries written (feed total: %d)", store_name, len(new_entries), len(data["deals"]))


def prune_expired() -> None:
    """Remove all entries whose valid_until has passed and refresh generated_at."""
    today_str = date.today().isoformat()
    data = _load()
    before = len(data.get("deals", []))
    data["deals"] = [d for d in data.get("deals", []) if d.get("valid_until", "9999") >= today_str]
    data["generated_at"] = _now_iso()
    after = len(data["deals"])
    if before != after:
        log.info("[deals] Pruned %d expired entries", before - after)
    _save(data)
