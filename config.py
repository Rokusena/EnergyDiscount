import os
import sys
from dotenv import load_dotenv

load_dotenv()

RESEND_API_KEY = os.getenv("RESEND_API_KEY", "")
TO_EMAIL       = [e.strip() for e in os.getenv("TO_EMAIL", "").split(",") if e.strip()]
FROM_EMAIL     = os.getenv("FROM_EMAIL", "")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")

if not all([RESEND_API_KEY, TO_EMAIL, FROM_EMAIL, OPENAI_API_KEY]):  # TO_EMAIL is a list
    sys.exit("[config] Missing required env vars: RESEND_API_KEY, TO_EMAIL, FROM_EMAIL, OPENAI_API_KEY")

BASE_URL = "https://www.raskakcija.lt"

# Stores that use slug-based catalog links on the homepage
STORES_SLUG = [
    {"name": "IKI",    "slug": "naujausias-iki-kaininis-katalogas"},
    {"name": "Lidl",   "slug": "naujausias-lidl-kaininis-katalogas"},
    {"name": "Maxima", "slug": "naujausias-maxima-kaininis-katalogas"},
    {"name": "Norfa",  "slug": "naujausias-norfa-kaininis-katalogas"},
    {"name": "Rimi",   "slug": "naujausias-rimi-kaininis-katalogas"},
]

# Stores with a dedicated leidinys page — scrape the page directly for images
STORES_LEIDINYS = [
    {"name": "Šilas",    "url": f"{BASE_URL}/silas-leidinys.htm"},
    {"name": "Promo",    "url": f"{BASE_URL}/promo-leidinys.htm"},
    {"name": "Aibė",     "url": f"{BASE_URL}/aibe-leidinys.htm"},
    {"name": "Vynoteka", "url": f"{BASE_URL}/vynoteka-leidinys.htm"},
]

# Primary keywords — any match on an OCR page triggers a deal
ENERGY_KEYWORDS = [
    "energetinis",
    "energinis",
    "energy",
    "monster",
    "redbull",
    "red bull",
    "burn",
    "hell",
    "rockstar",
    "battery",
]

# "gėrimas" only counts when one of these appears within 80 chars of it
DRINK_WORD = "gėrimas"
DRINK_CONTEXT_KEYWORDS = [
    "energetinis", "energinis", "monster", "redbull",
    "red bull", "burn", "hell", "rockstar", "battery", "energy",
]

MIN_OCR_CONFIDENCE = 60  # skip pages below this mean confidence %
