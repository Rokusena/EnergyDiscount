"""
Entry point.

  python main.py           → start scheduler (runs every Monday at 08:00)
  python main.py --run-now → single immediate run (for testing / manual trigger)
"""
import argparse
import logging
import sys
import time
from datetime import datetime

import schedule

from config       import OPENAI_API_KEY
from scraper      import find_catalog_urls, get_catalog_images
from ocr          import process_store_images
from email_sender import send_deals_email
from seen         import is_seen, mark_seen

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(name)s  %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%S",
)
log = logging.getLogger("main")


def run() -> None:
    log.info("=== Starting catalog scan ===")

    catalogs = find_catalog_urls()
    if not catalogs:
        log.info("No catalogs found. Exiting run.")
        return

    store_results = []

    for catalog in catalogs:
        store_name  = catalog["store_name"]
        catalog_url = catalog["catalog_url"]
        dates       = catalog["dates"]

        # Skip already-processed catalogs
        if is_seen(catalog_url):
            log.info("[%s] Already seen %s — skipping.", store_name, catalog_url)
            continue

        log.info("[%s] New catalog: %s", store_name, catalog_url)

        image_urls = get_catalog_images(catalog_url)
        if not image_urls:
            log.info("[%s] No images found — marking seen and skipping.", store_name)
            mark_seen(catalog_url, expires=dates.get("to"))
            continue

        try:
            deals = process_store_images(image_urls, OPENAI_API_KEY)
        except Exception as exc:
            log.error("[%s] Vision pipeline error: %s", store_name, exc)
            continue

        # Always mark seen so we don't reprocess on the next cron tick
        mark_seen(catalog_url, expires=dates.get("to"))

        log.info("[%s] Total unique deals found: %d", store_name, len(deals))

        if deals:
            # Adapt flat deal list → pages structure expected by email_sender
            # Each deal: {product, sale_price, regular_price, note}
            # email_sender expects matches with: {snippet, price, regular_price}
            matches = [
                {
                    "snippet":       _format_snippet(d),
                    "price":         f"{d['sale_price']} €" if d.get("sale_price") else None,
                    "regular_price": f"{d['regular_price']} €" if d.get("regular_price") else None,
                }
                for d in deals
            ]
            store_results.append({
                "store_name":  store_name,
                "catalog_url": catalog_url,
                "dates":       dates,
                "pages":       [{"page_index": 0, "image_url": "", "matches": matches}],
            })

    if not store_results:
        log.info("No energy drink deals found in any catalog. No email sent.")
        return

    log.info("Deals found in %d store(s). Sending summary email…", len(store_results))
    try:
        send_deals_email(store_results)
        log.info("Email sent successfully.")
    except Exception as exc:
        log.error("Failed to send email: %s", exc)

    log.info("=== Run complete ===")


# ---------------------------------------------------------------------------
# Entrypoint
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(description="Energy drink deal scraper")
    parser.add_argument(
        "--run-now",
        action="store_true",
        help="Run immediately instead of waiting for the Monday cron schedule",
    )
    args = parser.parse_args()

    if args.run_now:
        log.info("Manual run triggered via --run-now")
        run()
        return

    # Schedule: every Monday at 08:00 local time
    schedule.every().monday.at("08:00").do(run)
    log.info("Scheduler started. Next run: every Monday at 08:00.")
    log.info("Press Ctrl+C to stop.")

    try:
        while True:
            schedule.run_pending()
            time.sleep(30)  # check every 30 s
    except KeyboardInterrupt:
        log.info("Shutting down.")
        sys.exit(0)


def _format_snippet(deal: dict) -> str:
    """Build a human-readable product line from a GPT-4o deal dict."""
    parts = [deal.get("product", "")]
    if deal.get("note"):
        parts.append(f"({deal['note']})")
    return "  ".join(p for p in parts if p)


if __name__ == "__main__":
    main()
