"""
Fetches raskakcija.lt and returns catalog metadata + image URLs for each store.
Uses only requests + BeautifulSoup — no headless browser needed.
"""
import re
import logging
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

from config import BASE_URL, STORES_SLUG, STORES_LEIDINYS

log = logging.getLogger(__name__)

HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; EnergyBot/1.0)"}
TIMEOUT = 30


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def find_catalog_urls() -> list[dict]:
    """
    Returns a list of { store_name, catalog_url, dates: {from, to} }
    for every store with an active catalog.

    Two strategies:
      - STORES_SLUG: find catalog link on the homepage by slug pattern
      - STORES_LEIDINYS: treat the leidinys page itself as the catalog page
    """
    results = []
    results.extend(_find_slug_catalogs())
    results.extend(_find_leidinys_catalogs())
    return results


def get_catalog_images(catalog_url: str) -> list[str]:
    """
    Fetches a catalog detail page and returns all image URLs that look like
    catalog page scans (large raster images, not logos/icons).
    """
    log.info("Fetching catalog page: %s", catalog_url)
    try:
        resp = requests.get(catalog_url, headers=HEADERS, timeout=TIMEOUT)
        resp.raise_for_status()
    except requests.RequestException as exc:
        log.error("Failed to fetch catalog page %s: %s", catalog_url, exc)
        return []

    soup = BeautifulSoup(resp.text, "html.parser")
    seen: set[str] = set()
    urls: list[str] = []

    # 1. Collect from <img> tags (including lazy-load attributes)
    for img in soup.find_all("img"):
        for attr in ("data-src", "data-lazy-src", "data-original", "src"):
            src = img.get(attr, "")
            if src and src not in seen and _is_catalog_image(src):
                full = src if src.startswith("http") else urljoin(BASE_URL, src)
                seen.add(src)
                urls.append(full)
                break

    # 2. Collect image URLs embedded in <script> JSON blobs
    for script in soup.find_all("script"):
        text = script.string or ""
        for m in re.finditer(r'"(https?://[^"]+\.(?:jpg|jpeg|png|webp))"', text, re.IGNORECASE):
            src = m.group(1)
            if src not in seen and _is_catalog_image(src):
                seen.add(src)
                urls.append(src)

    log.info("Found %d catalog images on %s", len(urls), catalog_url)
    return urls


# ---------------------------------------------------------------------------
# Slug-based stores (IKI, Lidl, Maxima, Norfa, Rimi)
# ---------------------------------------------------------------------------

def _find_slug_catalogs() -> list[dict]:
    log.info("Fetching %s for slug-based catalogs…", BASE_URL)
    try:
        resp = requests.get(BASE_URL, headers=HEADERS, timeout=TIMEOUT)
        resp.raise_for_status()
    except requests.RequestException as exc:
        log.error("Failed to fetch homepage: %s", exc)
        return []

    soup = BeautifulSoup(resp.text, "html.parser")
    results = []

    for store in STORES_SLUG:
        slug = store["slug"]
        link = soup.find("a", href=re.compile(re.escape(slug)))
        if not link:
            log.info("No catalog link found for %s", store["name"])
            continue

        href = link["href"]
        catalog_url = href if href.startswith("http") else urljoin(BASE_URL, href)
        dates = _parse_dates(href)

        log.info("Found catalog for %s: %s (%s – %s)",
                 store["name"], catalog_url, dates["from"], dates["to"])
        results.append({"store_name": store["name"], "catalog_url": catalog_url, "dates": dates})

    return results


# ---------------------------------------------------------------------------
# Leidinys-page stores (Šilas, Promo, Aibė, Vynoteka)
# ---------------------------------------------------------------------------

def _find_leidinys_catalogs() -> list[dict]:
    """
    For stores with a fixed leidinys URL the page IS the catalog viewer.
    We scrape images directly from that page — each store's leidinys URL is
    unique so deduplication via seen_catalogs works correctly per-store.
    Dates are parsed from any dated link that belongs to that store's own slug.
    """
    results = []

    for store in STORES_LEIDINYS:
        name = store["name"]
        leidinys_url = store["url"]

        log.info("Fetching leidinys page for %s: %s", name, leidinys_url)
        try:
            resp = requests.get(leidinys_url, headers=HEADERS, timeout=TIMEOUT)
            resp.raise_for_status()
        except requests.RequestException as exc:
            log.error("Failed to fetch leidinys page for %s: %s", name, exc)
            continue

        soup = BeautifulSoup(resp.text, "html.parser")

        # Parse dates from page body text (leidinys pages embed dates in
        # a yellow banner like "nuo 2026.03.19 iki 2026.04.07" or
        # "Pasiūlymai galioja 2026 04 01 - 04 14").
        dates = _parse_dates_from_text(soup.get_text(" ", strip=True))
        if dates["to"] != "nežinoma":
            log.info("Dates for %s (from text): %s – %s", name, dates["from"], dates["to"])
        else:
            log.info("No dates found for %s", name)

        # Always use the leidinys URL itself — keeps per-store dedup correct.
        log.info("Catalog for %s: %s (%s – %s)",
                 name, leidinys_url, dates["from"], dates["to"])
        results.append({"store_name": name, "catalog_url": leidinys_url, "dates": dates})

    return results


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _is_catalog_image(src: str) -> bool:
    """Heuristic: exclude logos/icons, require a raster image extension."""
    if not src:
        return False
    low = src.lower()
    for skip in ("logo", "icon", "avatar", "banner", "sprite", "thumb"):
        if skip in low:
            return False
    return bool(re.search(r"\.(jpg|jpeg|png|webp)(\?|$)", low))


def _parse_dates_from_text(text: str) -> dict:
    """
    Extract catalog validity dates from the visible text of a leidinys page.

    Handles formats found on raskakcija.lt leidinys pages:
      1. "nuo 2026.03.19 iki 2026.04.07"   (dot-separated, both years present)
      2. "2026 04 01 - 04 14"              (space-separated, year only on start)
      3. "2026-04-01 – 2026-04-14"         (dash-separated full dates)
    """
    # Format 1: nuo YYYY.MM.DD iki YYYY.MM.DD
    m = re.search(
        r"nuo\s+(\d{4})[.\-](\d{2})[.\-](\d{2})\s+iki\s+(\d{4})[.\-](\d{2})[.\-](\d{2})",
        text, re.IGNORECASE,
    )
    if m:
        return {
            "from": f"{m.group(1)}-{m.group(2)}-{m.group(3)}",
            "to":   f"{m.group(4)}-{m.group(5)}-{m.group(6)}",
        }

    # Format 2: YYYY MM DD - MM DD  (year shared)
    m = re.search(
        r"(\d{4})\s+(\d{2})\s+(\d{2})\s*[-–]\s*(\d{2})\s+(\d{2})",
        text,
    )
    if m:
        year = m.group(1)
        return {
            "from": f"{year}-{m.group(2)}-{m.group(3)}",
            "to":   f"{year}-{m.group(4)}-{m.group(5)}",
        }

    # Format 3: YYYY-MM-DD – YYYY-MM-DD
    m = re.search(
        r"(\d{4}-\d{2}-\d{2})\s*[-–]\s*(\d{4}-\d{2}-\d{2})",
        text,
    )
    if m:
        return {"from": m.group(1), "to": m.group(2)}

    return {"from": "nežinoma", "to": "nežinoma"}


def _parse_dates(slug: str) -> dict:
    """
    Extract validity dates from a URL like:
      /naujausias-iki-kaininis-katalogas-20260406--20260412
    Returns { from: '2026-04-06', to: '2026-04-12' }.
    """
    m = re.search(r"(\d{8})--(\d{8})", slug)
    if not m:
        return {"from": "nežinoma", "to": "nežinoma"}

    def fmt(s):
        return f"{s[:4]}-{s[4:6]}-{s[6:8]}"

    return {"from": fmt(m.group(1)), "to": fmt(m.group(2))}
