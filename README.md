# EnergyDiscount

Scrapes Lithuanian grocery store catalogs from [raskakcija.lt](https://www.raskakcija.lt) and emails you when energy drinks are on sale. Runs automatically every day via GitHub Actions — no server needed. Each store's catalog page is only re-fetched once its last known validity window has actually expired, so the daily check stays cheap.

---

## How it works

1. **Scrape** — fetches the latest catalog page for each store, skipping any store whose last known catalog hasn't expired yet
2. **Pre-filter** — EasyOCR (Lithuanian + English) scans every page for energy drink keywords, free and open-source
3. **Extract** — GPT-4o vision analyses only the matching pages and returns structured deal data
4. **Email** — sends one HTML summary email via Resend with all deals grouped by store
5. **Publish** — writes currently-active deals to `deals.json` (product, price, discount, price/L, validity) for the companion portfolio site
6. **Deduplicate** — tracks processed catalogs in `seen_catalogs.json` so you only get emailed about new ones

---

## Stores monitored

IKI · Lidl · Maxima · Norfa · Rimi · Šilas · Promo · Aibė · Vynoteka

---

## Setup

### 1. Clone the repo

```bash
git clone https://github.com/yourusername/EnergyDiscount.git
cd EnergyDiscount
```

### 2. Install Python dependencies

```bash
pip install -r requirements.txt
```

No system OCR install needed — the pre-filter uses [EasyOCR](https://github.com/JaidedAI/EasyOCR) (Lithuanian + English), a pure-Python, open-source OCR engine. Its models (~100MB) download automatically on first run and are cached under `~/.EasyOCR` afterward.

### 3. Configure `.env`

```env
RESEND_API_KEY=re_xxxxxxxxxxxx
TO_EMAIL=you@example.com
FROM_EMAIL=deals@yourdomain.com
OPENAI_API_KEY=sk-...
```

- `TO_EMAIL` accepts multiple addresses: `a@x.com,b@x.com`
- `FROM_EMAIL` must be on a domain verified with Resend
- Get a Resend key at [resend.com](https://resend.com)
- Get an OpenAI key at [platform.openai.com](https://platform.openai.com)

### 4. Run manually

```bash
python main.py --run-now                 # ~75% of your cores
python main.py --run-now --workers 4     # pin the OCR pool size
```

| Flag / env var | Default | Purpose |
|---|---|---|
| `--workers` / `OCR_WORKERS` | ~75% of cores | Pages OCR'd in parallel |
| `--download-workers` / `DOWNLOAD_WORKERS` | 4 | Concurrent downloads — raising it makes raskakcija.lt reset connections |
| `MAX_OCR_PX` | 1200 | Pre-filter downscale; full-resolution images are still what GPT sees |

Note that EasyOCR already spreads a single page across every core, so raising
`--workers` far beyond your core count makes it slower, not faster — the
cheaper lever is `MAX_OCR_PX`.

---

## GitHub Actions (recommended)

The included workflow runs **daily at 09:00 Vilnius time** and commits `seen_catalogs.json`, `deals.json`, and `store_history.json` back to the repo so state persists between runs. A daily run doesn't mean daily API spend: each store is skipped until its last known catalog validity window actually expires, so most runs touch only the one or two stores that changed.

### Setup

1. Push the repo to GitHub

2. Add these repository secrets under **Settings → Secrets and variables → Actions**:

   | Secret | Value |
   |--------|-------|
   | `RESEND_API_KEY` | Your Resend API key |
   | `TO_EMAIL` | Recipient email(s), comma-separated |
   | `FROM_EMAIL` | Verified sender address |
   | `OPENAI_API_KEY` | Your OpenAI API key |

3. The workflow at `.github/workflows/scraper.yml` runs automatically. You can also trigger it manually from the **Actions** tab.

---

## Project structure

| File | Purpose |
|------|---------|
| `main.py` | Entry point — runs once with `--run-now` or schedules a daily run |
| `scraper.py` | Finds catalog URLs and image lists on raskakcija.lt |
| `ocr.py` | Two-stage pipeline: EasyOCR pre-filter + GPT-4o extraction |
| `email_sender.py` | Builds HTML email and sends via Resend |
| `seen.py` | Tracks processed catalogs; skips until expiry date passes |
| `cadence.py` | Logs each store's observed refresh cadence for anomaly detection |
| `deals.py` | Builds/prunes `deals.json`, the public feed for the portfolio site |
| `config.py` | All config in one place — env vars, store list, keywords |
| `seen_catalogs.json` | Auto-generated; committed by CI to persist state |
| `store_history.json` | Auto-generated; per-store catalog history for cadence.py |
| `deals.json` | Auto-generated; live deals feed consumed by the portfolio site |
| `.env` | Your secrets — never committed |

---

## Notes

- Only `/admin/contentfiles/` images are read — the site also serves small
  `/imgcache/<w>.<h>/` thumbnails and ads, which are over half of every page list
- Failed downloads are retried with backoff; if most of a catalog's pages still
  fail, the run raises instead of recording the store as "checked, nothing found"
- EasyOCR is used only as a free, open-source keyword filter — GPT does the actual extraction
- GPT-4o is called with batches of up to 4 images per request to minimise API cost
- Each store's catalog is re-checked automatically once its listed expiry date passes
- Prices are extracted by GPT-4o directly from the catalog images — verify before buying
