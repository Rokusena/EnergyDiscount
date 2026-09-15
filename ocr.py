"""
Two-stage OCR pipeline:
  Stage 1 — EasyOCR pre-filter, Lithuanian + English (~0.5-1s/page after
            a one-time model load, free, open-source)
  Stage 2 — GPT-4o vision on candidates only, batched 4 images per call
"""
import base64
import io
import json
import logging
import os
import time
from concurrent.futures import ThreadPoolExecutor
from itertools import islice

import numpy as np
import requests
from PIL import Image
from openai import OpenAI

log = logging.getLogger(__name__)


class ExtractionError(Exception):
    """
    Raised when a batch could not be processed at all (API/network failure).
    Callers must treat this differently from an empty result: an empty list
    means "no energy drinks on these pages", this means "we never found out".
    """


# Lazily initialized: loading the EasyOCR models takes ~20-30s, so this
# happens once per process run on first use, not per image.
_reader = None


def _get_reader():
    global _reader
    if _reader is None:
        import easyocr
        import torch

        # Each worker OCRs its own page, so give each one a slice of the cores
        # instead of letting every torch op fight over all of them.
        torch.set_num_threads(max(1, (os.cpu_count() or 4) // OCR_WORKERS))
        log.info("  [filter] Loading EasyOCR models (lt+en), %d workers…", OCR_WORKERS)
        _reader = easyocr.Reader(["lt", "en"], gpu=False, verbose=False)
    return _reader


HEADERS          = {"User-Agent": "Mozilla/5.0 (compatible; EnergyBot/1.0)"}
DOWNLOAD_TIMEOUT = 60
API_TIMEOUT      = 60
MODEL = "gpt-5.6-luna"
BATCH_SIZE       = 4

# Pages are downloaded and OCR'd across a pool; override with OCR_WORKERS=n.
# ~75% of cores, leaving headroom so the box stays usable (and so the 4-core
# GitHub runner isn't fully saturated). All workers share one loaded model,
# so RAM does not scale with this number.
OCR_WORKERS = int(os.getenv("OCR_WORKERS") or 0) or max(2, int((os.cpu_count() or 4) * 0.75))

# Downloads stay deliberately gentle regardless of OCR_WORKERS: raskakcija.lt
# resets connections when too many land at once, and a refused page is a page
# of deals we never see.
DOWNLOAD_WORKERS  = int(os.getenv("DOWNLOAD_WORKERS") or 4)
DOWNLOAD_ATTEMPTS = 3

# Backstop for anything that slips past the URL filter in scraper.py.
MIN_PAGE_PX = 500

# OCR cost scales with pixel area, and EasyOCR already spreads one image across
# every core — so shrinking the image is the only real speed lever. Catalog
# offers are large display text that survives this easily: at 1200px a page
# takes ~3.5s instead of ~7.1s with identical keyword hits.
MAX_OCR_PX = int(os.getenv("MAX_OCR_PX") or 1200)

# A store whose pages mostly failed to download hasn't been checked — it just
# looks that way. Below this success ratio we raise instead of reporting "none".
MIN_DOWNLOAD_RATIO = 0.8

FILTER_KEYWORDS = [
    "energetinis", "energinis", "energy", "monster", "red bull", "redbull",
    "burn", "hell", "rockstar", "battery", "dynamit", "cult", "go!", "kong",
]

EXTRACTION_PROMPT = """\
You are extracting energy drink deals from one or more Lithuanian grocery \
store catalog page images sent in this message.

Return ONLY a JSON array. No explanation. No markdown fences.
If nothing matches across all pages, return [].

Match ONLY:
- Energy drinks: energetinis gėrimas, energinis gėrimas
- Brands (any size/flavor): Monster, Red Bull, Burn, Rockstar,
  Battery, Hell, Dynamit, Cult, Go!, Kong

Each item:
{
  "product": "brand + size + variant, e.g. Monster Mega 0.553l",
  "sale_price": "TIK / akcijos price as string, e.g. 1.29",
  "regular_price": "įprasta kaina as string, or null",
  "note": "promo mechanic like 1+1, -40%, or null"
}

Rules:
- TIK price (big number, red/yellow label) = sale_price
- įprasta kaina (smaller, often crossed out) = regular_price
- One entry per unique product across ALL pages — deduplicate
- Return [] if nothing matches\
"""

# Module-level cache: URL → raw bytes
# Populated during Stage 1 so Stage 2 doesn't re-download.
_image_cache: dict[str, bytes] = {}


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def filter_candidate_pages(image_urls: list[str]) -> list[str]:
    """
    Stage 1: Run EasyOCR on every page. Return only URLs whose OCR text
    contains at least one energy drink keyword.
    - Pages are downloaded and OCR'd across OCR_WORKERS threads.
    - Images too small to be catalog scans skip OCR entirely.
    - On OCR failure: include the page anyway (fail-safe).
    - Downloaded bytes are cached for Stage 2.
    """
    # Phase 1 — fetch pages on a small pool so we don't trip the site's
    # connection limits. Retries happen inside _download.
    with ThreadPoolExecutor(max_workers=DOWNLOAD_WORKERS) as pool:
        fetched = list(pool.map(lambda u: (u, _download(u)), image_urls))

    for url, data in fetched:
        if data is not None:
            _image_cache[url] = data

    pages = [(url, data) for url, data in fetched if data is not None]
    log.info("  [filter] %d/%d pages downloaded, OCR on %d workers…",
             len(pages), len(image_urls), OCR_WORKERS)

    # Load the models before any worker runs, so threads share one ready
    # reader rather than racing to build their own.
    reader = _get_reader()

    def check(page: tuple[str, bytes]) -> tuple[str, bool]:
        url, data = page
        filename = url.split("/")[-1]
        try:
            image = Image.open(io.BytesIO(data)).convert("RGB")
            if max(image.size) < MIN_PAGE_PX:
                log.info("  [filter] %s — not a catalog page (%dpx)", filename, max(image.size))
                return url, False
            if max(image.size) > MAX_OCR_PX:
                ratio = MAX_OCR_PX / max(image.size)
                image = image.resize((int(image.width * ratio), int(image.height * ratio)), Image.LANCZOS)
            pieces = reader.readtext(np.array(image), detail=0, paragraph=True)
            lower  = " ".join(pieces).lower()
            hit    = any(kw in lower for kw in FILTER_KEYWORDS)
        except Exception as exc:
            log.warning("  [filter] %s — OCR error (%s), keeping as candidate", filename, exc)
            return url, True

        if not hit:
            log.info("  [filter] %s — skipped", filename)
        return url, hit

    # Phase 2 — OCR in parallel; this is the CPU-bound part.
    with ThreadPoolExecutor(max_workers=OCR_WORKERS) as pool:
        results = list(pool.map(check, pages))

    return [url for url, hit in results if hit]


def extract_deals_from_batch(image_urls: list[str], api_key: str) -> list[dict]:
    """
    Stage 2: Send up to BATCH_SIZE images in one GPT-4o call.
    Images are read from the module cache when available.
    Returns a flat list of deal dicts.
    """
    if not image_urls:
        return []

    content: list[dict] = []
    for url in image_urls:
        data = _image_cache.get(url) or _download(url)
        if data is None:
            continue
        b64  = base64.b64encode(data).decode("utf-8")
        mime = _mime_type(url)
        content.append({
            "type": "image_url",
            "image_url": {
                "url":    f"data:{mime};base64,{b64}",
                "detail": "high",
            },
        })

    if not content:
        # We had pages to check but couldn't fetch a single one — a failure,
        # not a verdict of "no energy drinks here".
        raise ExtractionError(f"all {len(image_urls)} page image(s) failed to download")

    content.append({"type": "text", "text": EXTRACTION_PROMPT})

    client = OpenAI(api_key=api_key, timeout=API_TIMEOUT)

    for attempt in (1, 2):
        try:
            response = client.chat.completions.create(
                model=MODEL,
                messages=[{"role": "user", "content": content}],
                max_completion_tokens=2048,
            )
            break
        except Exception as exc:
            if getattr(exc, "status_code", None) == 429 and attempt == 1:
                log.warning("  [gpt4o] Rate limited, retrying in 10s…")
                time.sleep(10)
                continue
            raise ExtractionError(f"vision API call failed: {exc}") from exc

    raw   = response.choices[0].message.content or ""
    deals = _parse_response(raw)
    log.info("  [gpt4o] Sending batch of %d pages → %d deals found", len(image_urls), len(deals))
    return deals


def process_store_images(image_urls: list[str], api_key: str) -> list[dict]:
    """
    Orchestrates the two-stage pipeline:
      1. Tesseract pre-filter → candidates
      2. GPT-4o in batches of BATCH_SIZE → deals
      3. Deduplicate by lowercased product name
    """
    _image_cache.clear()

    candidates = filter_candidate_pages(image_urls)

    # _image_cache holds exactly the pages that downloaded. If most of them
    # failed, we never actually inspected this catalog — say so rather than
    # letting it be recorded as "checked, nothing found".
    if image_urls and len(_image_cache) < len(image_urls) * MIN_DOWNLOAD_RATIO:
        raise ExtractionError(
            f"only {len(_image_cache)}/{len(image_urls)} page images downloaded"
        )

    seen_products: set[str] = set()
    all_deals: list[dict]   = []

    for batch in _chunks(candidates, BATCH_SIZE):
        for deal in extract_deals_from_batch(batch, api_key):
            key = deal.get("product", "").lower().strip()
            if key and key not in seen_products:
                seen_products.add(key)
                all_deals.append(deal)

    log.info(
        "  [ocr] %d pages → %d candidates → %d deals found",
        len(image_urls), len(candidates), len(all_deals),
    )
    return all_deals


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _download(url: str, attempts: int = DOWNLOAD_ATTEMPTS) -> bytes | None:
    """
    Fetch one page image, retrying transient failures. raskakcija.lt resets
    connections when hit too hard, and a dropped page is a page of deals we
    never see — so it's worth a few retries with a widening backoff.
    """
    for attempt in range(1, attempts + 1):
        try:
            resp = requests.get(url, headers=HEADERS, timeout=DOWNLOAD_TIMEOUT)
            resp.raise_for_status()
            return resp.content
        except Exception as exc:
            if attempt == attempts:
                log.warning("  [ocr] Failed to download %s after %d attempts: %s",
                            url.split("/")[-1], attempts, exc)
                return None
            time.sleep(attempt)  # 1s, 2s, … give the server room to recover
    return None


def _mime_type(url: str) -> str:
    low = url.lower().split("?")[0]
    if low.endswith(".png"):
        return "image/png"
    if low.endswith(".webp"):
        return "image/webp"
    return "image/jpeg"


def _parse_response(raw: str) -> list[dict]:
    text = raw.strip()
    if text.startswith("```"):
        lines = text.splitlines()
        text  = "\n".join(lines[1:-1] if lines[-1].strip() == "```" else lines[1:])
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError as exc:
        log.error("  [gpt4o] JSON parse error: %s | raw: %.200s", exc, raw)
        return []
    if isinstance(parsed, dict):
        parsed = [parsed]
    if not isinstance(parsed, list):
        log.error("  [gpt4o] Unexpected response type: %s", type(parsed))
        return []
    return parsed


def _chunks(lst: list, size: int):
    it = iter(lst)
    while chunk := list(islice(it, size)):
        yield chunk
