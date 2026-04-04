# EnergyDiscount

Monitors Lithuanian grocery store deal catalogs and emails you when energy drinks are on sale.

Scrapes [raskakcija.lt](https://www.raskakcija.lt), runs OCR on each catalog page image (Tesseract, Lithuanian), filters for energy drink keywords, and sends a formatted HTML email via [Resend](https://resend.com).

## Stores monitored

IKI · Lidl · Maxima · Norfa · Rimi · Šilas · Promo · Aibė · Vynoteka · Senukai · Ermitažas · JYSK · Moki Veži

## Keywords detected

`energetinis` · `energinis` · `energy` · `monster` · `redbull` · `red bull` · `burn` · `hell` · `rockstar` · `battery` · `gėrimas` (near brand name)

---

## Setup

### 1. Prerequisites

- Python 3.11+
- **Tesseract OCR** installed system-wide with Lithuanian language data:

  **Ubuntu / Debian**
  ```bash
  sudo apt install tesseract-ocr tesseract-ocr-lit
  ```

  **macOS (Homebrew)**
  ```bash
  brew install tesseract
  # Then download the Lithuanian trained data:
  # https://github.com/tesseract-ocr/tessdata/blob/main/lit.traineddata
  # Place it in: $(brew --prefix)/share/tessdata/
  ```

  **Windows**
  - Download and run the installer from https://github.com/UB-Mannheim/tesseract/wiki
  - During install tick "Lithuanian" under additional language data
  - Add the install directory (e.g. `C:\Program Files\Tesseract-OCR`) to your `PATH`

- A [Resend](https://resend.com) account with an API key and a verified sender domain

### 2. Create a virtual environment and install dependencies

```bash
python -m venv .venv

# Windows
.venv\Scripts\activate

# macOS / Linux
source .venv/bin/activate

pip install -r requirements.txt
```

### 3. Configure environment variables

Edit `.env`:

```env
RESEND_API_KEY=re_xxxxxxxxxxxx
TO_EMAIL=you@example.com
FROM_EMAIL=deals@yourdomain.com
```

> `FROM_EMAIL` must be on a domain you have verified with Resend.

---

## Running

### Run once immediately (testing / manual trigger)

```bash
python main.py --run-now
```

### Run on a schedule (every Monday at 08:00 local time)

```bash
python main.py
```

The process stays alive and fires automatically each Monday. Use a process manager (below) to keep it running.

---

## Hosting on a VPS

### Option A — systemd (recommended)

Create `/etc/systemd/system/energy-discount.service`:

```ini
[Unit]
Description=EnergyDiscount Scraper
After=network.target

[Service]
WorkingDirectory=/home/youruser/EnergyDiscount
ExecStart=/home/youruser/EnergyDiscount/.venv/bin/python main.py
Restart=on-failure
EnvironmentFile=/home/youruser/EnergyDiscount/.env
User=youruser

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl enable energy-discount
sudo systemctl start energy-discount
journalctl -u energy-discount -f    # watch logs
```

### Option B — screen / tmux (quick & dirty)

```bash
screen -S energy
python main.py
# Ctrl+A then D to detach
```

---

## How it works

```
main.py  (schedule: every Monday 08:00)
  └── scraper.py      → finds latest catalog URLs on raskakcija.lt
  └── scraper.py      → fetches each catalog page, extracts image URLs
  └── ocr.py          → downloads images, runs Tesseract (Lithuanian + English),
                         filters for energy drink keywords, extracts prices
  └── seen.py         → skips catalogs already processed (seen_catalogs.json)
  └── email_sender.py → sends one HTML summary email via Resend
```

## File overview

| File | Purpose |
|------|---------|
| `main.py` | Entry point + Monday scheduler |
| `scraper.py` | Finds catalog URLs and image lists on raskakcija.lt |
| `ocr.py` | OCR pipeline — keyword filtering + price extraction |
| `email_sender.py` | HTML email builder + Resend sender |
| `seen.py` | Persistent deduplication via `seen_catalogs.json` |
| `config.py` | Env vars, store list, keywords, OCR confidence threshold |
| `requirements.txt` | Python dependencies |
| `.env` | Your secrets (not committed to git) |

---

## Notes

- OCR pages with mean confidence below 60 % are skipped automatically.
- Images are processed **sequentially** to keep memory usage low.
- `seen_catalogs.json` is created automatically on first run.
- Prices extracted from OCR snippets are best-effort — always verify before buying.
