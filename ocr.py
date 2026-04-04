"""
Two-stage OCR pipeline:
  Stage 1 — Tesseract pre-filter (~0.3s/page, free)
  Stage 2 — GPT-4o vision on candidates only, batched 4 images per call
"""
import base64
import io
import json
import logging
import time
from itertools import islice

import sys

import requests
import pytesseract
from PIL import Image
from openai import OpenAI

log = logging.getLogger(__name__)

if sys.platform == "win32":
    pytesseract.pytesseract.tesseract_cmd = r"C:\Program Files\Tesseract-OCR\tesseract.exe"

HEADERS          = {"User-Agent": "Mozilla/5.0 (compatible; EnergyBot/1.0)"}
DOWNLOAD_TIMEOUT = 60
API_TIMEOUT      = 60
MODEL            = "gpt-4o"
BATCH_SIZE       = 4

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
    Stage 1: Run Tesseract on every page. Return only URLs whose OCR text
    contains at least one energy drink keyword.
    - On Tesseract failure: include the page anyway (fail-safe).
    - Downloaded bytes are cached for Stage 2.
    """
    candidates = []

    for url in image_urls:
        filename = url.split("/")[-1]

        data = _download(url)
        if data is None:
            log.info("  [filter] %s — download failed, skipping", filename)
            continue
        _image_cache[url] = data

        try:
            image = Image.open(io.BytesIO(data)).convert("RGB")
            text  = pytesseract.image_to_string(image, lang="lit+eng", config="--psm 3")
            lower = text.lower()
            hit   = any(kw in lower for kw in FILTER_KEYWORDS)
        except Exception as exc:
            log.warning("  [filter] %s — Tesseract error (%s), keeping as candidate", filename, exc)
            candidates.append(url)
            continue

        if hit:
            candidates.append(url)
        else:
            log.info("  [filter] %s — skipped", filename)

    return candidates


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
        return []

    content.append({"type": "text", "text": EXTRACTION_PROMPT})

    client = OpenAI(api_key=api_key, timeout=API_TIMEOUT)

    for attempt in (1, 2):
        try:
            response = client.chat.completions.create(
                model=MODEL,
                messages=[{"role": "user", "content": content}],
                max_tokens=2048,
            )
            break
        except Exception as exc:
            if getattr(exc, "status_code", None) == 429 and attempt == 1:
                log.warning("  [gpt4o] Rate limited, retrying in 10s…")
                time.sleep(10)
                continue
            log.error("  [gpt4o] API error: %s", exc)
            return []

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

def _download(url: str) -> bytes | None:
    try:
        resp = requests.get(url, headers=HEADERS, timeout=DOWNLOAD_TIMEOUT)
        resp.raise_for_status()
        return resp.content
    except Exception as exc:
        log.warning("  [ocr] Failed to download %s: %s", url.split("/")[-1], exc)
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
