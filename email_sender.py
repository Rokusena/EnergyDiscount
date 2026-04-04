"""Builds and sends the HTML deals summary email via Resend."""
import html
import logging
from datetime import date

import resend

from config import RESEND_API_KEY, TO_EMAIL, FROM_EMAIL

resend.api_key = RESEND_API_KEY
log = logging.getLogger(__name__)


def send_deals_email(store_results: list[dict]) -> None:
    """
    store_results: list of {
        store_name, catalog_url, dates: {from, to},
        pages: [{ page_index, image_url, matches: [{keyword, snippet, price, regular_price}] }]
    }
    """
    today = date.today().strftime("%Y-%m-%d")
    subject = f"🔋 Energetiniai gėrimai akcijoje – {today}"

    body_html  = _build_html(store_results, today)
    body_plain = _build_plain(store_results, today)

    log.info("Sending email to %s …", TO_EMAIL)

    params = {
        "from":    FROM_EMAIL,
        "to":      TO_EMAIL,
        "subject": subject,
        "html":    body_html,
        "text":    body_plain,
    }
    response = resend.Emails.send(params)
    log.info("Email sent! id=%s", response.get("id"))


# ---------------------------------------------------------------------------
# HTML builder
# ---------------------------------------------------------------------------

def _build_html(store_results: list[dict], today: str) -> str:
    sections = "\n".join(_store_section(r) for r in store_results)

    return f"""<!DOCTYPE html>
<html lang="lt">
<head><meta charset="UTF-8"><title>Energetiniai gėrimai akcijoje</title></head>
<body style="font-family:Arial,sans-serif;max-width:800px;margin:0 auto;padding:20px;color:#333;">

  <div style="background:linear-gradient(135deg,#667eea,#764ba2);padding:30px;
              border-radius:8px;text-align:center;margin-bottom:30px;">
    <h1 style="color:#fff;margin:0;font-size:24px;">
      ⚡ Rasti pasiūlymai energetiniams gėrimams
    </h1>
    <p style="color:rgba(255,255,255,0.85);margin:8px 0 0;">{h(today)}</p>
  </div>

  {sections}

  <hr style="margin-top:40px;border:none;border-top:1px solid #eee;">
  <p style="color:#aaa;font-size:12px;text-align:center;">
    Duomenys iš <a href="https://www.raskakcija.lt" style="color:#aaa;">raskakcija.lt</a> •
    Kainos ir tekstas išgauti automatiškai per OCR ir gali būti netikslūs
  </p>
</body>
</html>"""


def _store_section(result: dict) -> str:
    store_name  = result["store_name"]
    catalog_url = result["catalog_url"]
    dates       = result["dates"]
    all_matches = [m for page in result["pages"] for m in page["matches"]]

    rows = "\n".join(
        f"""<tr>
          <td style="padding:6px 10px;border-bottom:1px solid #eee;">{h(m['snippet'][:120])}</td>
          <td style="padding:6px 10px;border-bottom:1px solid #eee;color:#c0392b;">
            <strong>{h(m['price'] or '–')}</strong>
          </td>
          <td style="padding:6px 10px;border-bottom:1px solid #eee;color:#888;">
            {'<s>' + h(m['regular_price']) + '</s>' if m['regular_price'] else '–'}
          </td>
        </tr>"""
        for m in all_matches
    )

    return f"""
<h2 style="margin-top:32px;color:#2c3e50;border-bottom:2px solid #3498db;padding-bottom:6px;">
  🏪 {h(store_name)}
</h2>
<p style="color:#888;font-size:13px;">
  Katalogas galioja: <strong>{h(dates['from'])}</strong> – <strong>{h(dates['to'])}</strong> |
  <a href="{h(catalog_url)}" style="color:#3498db;">Peržiūrėti katalogą</a>
</p>
<table style="border-collapse:collapse;width:100%;font-size:14px;">
  <thead>
    <tr style="background:#f4f6f9;">
      <th style="padding:8px 10px;text-align:left;border-bottom:2px solid #ddd;">Produktas</th>
      <th style="padding:8px 10px;text-align:left;border-bottom:2px solid #ddd;">Akcijos kaina</th>
      <th style="padding:8px 10px;text-align:left;border-bottom:2px solid #ddd;">Įprasta kaina</th>
    </tr>
  </thead>
  <tbody>{rows}</tbody>
</table>"""


# ---------------------------------------------------------------------------
# Plain-text fallback
# ---------------------------------------------------------------------------

def _build_plain(store_results: list[dict], today: str) -> str:
    lines = [f"Energetiniai gėrimai akcijoje – {today}", "=" * 50, ""]
    for r in store_results:
        lines.append(f"{r['store_name']}  ({r['dates']['from']} – {r['dates']['to']})")
        lines.append("-" * 40)
        for page in r["pages"]:
            for m in page["matches"]:
                price_str = m["price"] or ""
                if m["regular_price"]:
                    price_str += f"  (buvo {m['regular_price']})"
                lines.append(f"• {m['snippet'][:100].strip()}  {price_str}")
        lines.append("")
    lines.append("Duomenys iš raskakcija.lt")
    return "\n".join(lines)


def h(text) -> str:
    """HTML-escape helper."""
    return html.escape(str(text)) if text else ""
