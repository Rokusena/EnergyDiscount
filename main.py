"""
Entry point.

  python main.py           → start scheduler (runs daily at 08:00)
  python main.py --run-now → single immediate run (for testing / manual trigger)
"""
import argparse
import logging
import sys
import time
from datetime import date, datetime, timezone

import schedule

from config       import OPENAI_API_KEY
from scraper      import find_catalog_urls, get_catalog_images
from ocr          import process_store_images
from email_sender import send_deals_email
from seen         import is_seen, mark_seen
from cadence      import record_catalog, get_cadence, check_anomaly
from deals        import update_deals, prune_expired

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
        prune_expired()
        return

    store_results = []
    today   = date.today()
    now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    for catalog in catalogs:
        store_name  = catalog["store_name"]
        catalog_url = catalog["catalog_url"]
        dates       = catalog["dates"]

        if is_seen(catalog_url):
            log.info("[%s] Already seen %s — skipping.", store_name, catalog_url)
            continue

        # is_seen() already proves this catalog URL is genuinely new — that's ground
        # truth and always wins. Cadence is recorded and checked for anomalies only;
        # it never gates whether a known-new catalog gets processed.
        record_catalog(store_name, catalog_url, now_iso, dates.get("to"))
        check_anomaly(store_name, catalog_url, today)

        cadence = get_cadence(store_name)
        if cadence:
            log.info("[%s] Observed cadence: every ~%d days on %s (n=%d)",
                     store_name, cadence["avg_interval_days"], cadence["weekday"], cadence["sample_size"])

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

        mark_seen(catalog_url, expires=dates.get("to"))
        log.info("[%s] Total unique deals found: %d", store_name, len(deals))

        scraped_at  = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        valid_until = dates.get("to", "")

        # Update deals.json for this store (even if empty — clears stale entries).
        if valid_until and valid_until != "nežinoma":
            update_deals(store_name, deals, valid_until, scraped_at, catalog_url)

        if deals:
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

    # Always prune expired entries and refresh generated_at, even on no-new-deal runs.
    prune_expired()

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

    # Schedule: every day at 08:00 local time
    schedule.every().day.at("08:00").do(run)
    log.info("Scheduler started. Next run: daily at 08:00.")
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
