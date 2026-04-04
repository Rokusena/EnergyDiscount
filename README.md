# EnergyDiscount

Scrapes Lithuanian grocery store catalogs from [raskakcija.lt](https://www.raskakcija.lt) and emails you when energy drinks are on sale. Runs automatically every week via GitHub Actions — no server needed.

---

## How it works

1. **Scrape** — fetches the latest catalog page for each store
2. **Pre-filter** — Tesseract OCR scans every page for energy drink keywords (~0.3s/page, free)
3. **Extract** — GPT-4o vision analyses only the matching pages and returns structured deal data
4. **Email** — sends one HTML summary email via Resend with all deals grouped by store
5. **Deduplicate** — tracks processed catalogs in `seen_catalogs.json` so you only get emailed about new ones

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

### 2. Install Tesseract with Lithuanian language data

**Windows**
- Download the installer from [UB-Mannheim/tesseract](https://github.com/UB-Mannheim/tesseract/wiki)
- During install, tick **Lithuanian** under additional language data
- Default install path: `C:\Program Files\Tesseract-OCR\`

**Ubuntu / Debian**
```bash
sudo apt install tesseract-ocr tesseract-ocr-lit
```

**macOS**
```bash
brew install tesseract
# Download lit.traineddata from github.com/tesseract-ocr/tessdata
# Place it in: $(brew --prefix)/share/tessdata/
```

### 3. Install Python dependencies

```bash
pip install -r requirements.txt
```

### 4. Configure `.env`

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

### 5. Run manually

```bash
python main.py --run-now
```

---

## GitHub Actions (recommended)

The included workflow runs every **Monday and Tuesday at 09:00 Vilnius time** and commits `seen_catalogs.json` back to the repo so state persists between runs.

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
| `main.py` | Entry point — runs once with `--run-now` or schedules weekly |
| `scraper.py` | Finds catalog URLs and image lists on raskakcija.lt |
| `ocr.py` | Two-stage pipeline: Tesseract pre-filter + GPT-4o extraction |
| `email_sender.py` | Builds HTML email and sends via Resend |
| `seen.py` | Tracks processed catalogs; skips until expiry date passes |
| `config.py` | All config in one place — env vars, store list, keywords |
| `seen_catalogs.json` | Auto-generated; committed by CI to persist state |
| `.env` | Your secrets — never committed |

---

## Notes

- Catalog pages are processed sequentially to keep memory usage low
- Tesseract is used only as a cheap keyword filter — GPT-4o does the actual extraction
- GPT-4o is called with batches of up to 4 images per request to minimise API cost
- Each store's catalog is re-checked automatically once its listed expiry date passes
- Prices are extracted by GPT-4o directly from the catalog images — verify before buying
