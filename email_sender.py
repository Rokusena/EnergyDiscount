"""Builds and sends the HTML deals summary email via Resend — Receipt design."""
import html
import logging
import re
from datetime import date, datetime, timedelta

import resend

from config import RESEND_API_KEY, TO_EMAIL, FROM_EMAIL

resend.api_key = RESEND_API_KEY
log = logging.getLogger(__name__)

_MONO   = "'SF Mono','Menlo','Consolas','Courier New',monospace"
_M      = "#ff2e9a"   # hot magenta
_INK    = "#2a2330"
_MUTED  = "#8a7f92"
_DASH   = "#c8bfcf"
_PAPER  = "#fbf8fd"
_BG     = "#f0ebf2"


def send_deals_email(store_results: list[dict]) -> None:
    today      = date.today().strftime("%Y-%m-%d")
    subject    = f"\u26a1 Energetiniai g\u0117rimai akcijoje \u2013 {today}"
    body_html  = _build_html(store_results, today)
    body_plain = _build_plain(store_results, today)

    for recipient in TO_EMAIL:
        log.info("Sending email to %s \u2026", recipient)
        response = resend.Emails.send({
            "from":    FROM_EMAIL,
            "to":      [recipient],
            "subject": subject,
            "html":    body_html,
            "text":    body_plain,
        })
        log.info("Email sent to %s id=%s", recipient, response.get("id"))


# ── price helpers ─────────────────────────────────────────────────────────────

def h(text) -> str:
    return html.escape(str(text)) if text else ""


def _parse_price(s: str) -> float | None:
    if not s:
        return None
    clean = re.sub(r"[^\d,.]", "", s).replace(",", ".")
    try:
        return float(clean)
    except ValueError:
        return None


def _discount_pct(price: str, regular_price: str) -> int | None:
    p, rp = _parse_price(price), _parse_price(regular_price)
    if p and rp and rp > 0 and p < rp:
        return int(round((rp - p) / rp * 100))
    return None


def _find_cheapest(store_results: list[dict]):
    best_val, best = float("inf"), None
    for r in store_results:
        for pg in r["pages"]:
            for m in pg["matches"]:
                val = _parse_price(m.get("price", ""))
                if val is not None and val < best_val:
                    best_val = val
                    best = (m["snippet"][:30].strip(), m["price"], r["store_name"])
    return best


def _best_discount_label(store_results: list[dict]) -> str:
    best_pct, label = 0, "\u2013"
    for r in store_results:
        for pg in r["pages"]:
            for m in pg["matches"]:
                pct = _discount_pct(m.get("price", ""), m.get("regular_price", ""))
                if pct and pct > best_pct:
                    best_pct = pct
                    label = f"\u2212{pct}% ({m['snippet'][:20].strip()} \u00b7 {r['store_name']})"
    if best_pct == 0:
        for r in store_results:
            for pg in r["pages"]:
                for m in pg["matches"]:
                    hit = re.search(r"(\d+)\s*%", m["snippet"])
                    if hit:
                        pct = int(hit.group(1))
                        if pct > best_pct:
                            best_pct = pct
                            label = f"\u2212{pct}% ({r['store_name']})"
    return label


# ── HTML builder ──────────────────────────────────────────────────────────────

def _build_html(store_results: list[dict], today: str) -> str:
    dt       = datetime.strptime(today, "%Y-%m-%d")
    week_num = dt.isocalendar()[1]
    date_disp = today.replace("-", "\u00b7")
    mon      = dt - timedelta(days=dt.weekday())
    sun      = mon + timedelta(days=6)
    week_lbl = f"W{week_num:02d} \u00b7 {mon.strftime('%m\u00b7%d')} \u2192 {sun.strftime('%m\u00b7%d')}"

    all_matches = [m for r in store_results for pg in r["pages"] for m in pg["matches"]]
    n_deals  = len(all_matches)
    n_stores = len(store_results)

    cheapest       = _find_cheapest(store_results)
    cheapest_line  = f"{cheapest[0]} \u2192 {cheapest[1]}" if cheapest else "\u2013"
    cheapest_chip  = (
        f'<span style="background:{_M};color:#fff;font-weight:800;padding:2px 8px;">{h(cheapest[1])}</span>'
        if cheapest else "\u2013"
    )
    best_disc = _best_discount_label(store_results)

    if n_deals == 1:
        rado = "1 PASI\u016eLYMAS"
    elif n_deals in (2, 3, 4):
        rado = f"{n_deals} PASI\u016eLYMAI"
    else:
        rado = f"{n_deals} PASI\u016eLYM\u0172"

    store_blocks = "\n".join(_store_block(i + 1, r) for i, r in enumerate(store_results))
    cta_rows     = "\n".join(_cta_row(r, i) for i, r in enumerate(store_results))

    return f"""<!DOCTYPE html>
<html lang="lt">
<head>
<meta charset="UTF-8">
<title>Energetiniai g\u0117rimai akcijoje \u2013 {h(today)}</title>
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="color-scheme" content="light dark">
<meta name="supported-color-schemes" content="light dark">
<!--[if mso]>
<style type="text/css">
  table, td, div, h1, p {{ font-family: Courier New, monospace !important; }}
</style>
<![endif]-->
<style>
  @media (prefers-color-scheme: dark) {{
    body {{ background: #0d0a10 !important; color: #f2edf5 !important; }}
    body table, body td {{ background: #0d0a10 !important; }}
    .paper {{ background: #16121a !important; }}
    .muted  {{ color: #8a7f92 !important; }}
    .dash   {{ color: #3a2f42 !important; }}
    .ink    {{ color: #f2edf5 !important; }}
    .big-headline {{ color: #f2edf5 !important; }}
    .strike {{ color: #5a4a62 !important; }}
    .rule2  {{ border-top-color: #2a2330 !important; }}
    a.ink   {{ color: #f2edf5 !important; }}
  }}
  @media only screen and (max-width: 620px) {{
    .container {{ width: 100% !important; }}
    .px        {{ padding-left: 18px !important; padding-right: 18px !important; }}
    .big-price {{ font-size: 28px !important; }}
    .big-headline {{ font-size: 34px !important; }}
  }}
</style>
</head>
<body style="margin:0;padding:0;background:{_BG};font-family:{_MONO};-webkit-font-smoothing:antialiased;">
<div style="display:none;max-height:0;overflow:hidden;">KVITAS // {n_stores} parduotuv{'ė' if n_stores == 1 else 'ės'} rado akcij\u0173 \u0161i\u0105 savait\u0119.</div>

<table role="presentation" cellpadding="0" cellspacing="0" border="0" width="100%" style="background:{_BG};">
<tr><td align="center" style="padding:28px 12px;">
<table role="presentation" class="container paper" cellpadding="0" cellspacing="0" border="0" width="560" style="width:560px;max-width:560px;background:{_PAPER};">

  <tr><td class="px" style="padding:28px 28px 6px 28px;text-align:center;">
    <div style="font-family:{_MONO};font-size:11px;letter-spacing:0.22em;color:{_M};font-weight:700;">R \u00b7 A \u00b7 S \u00b7 K \u00b7 A \u00b7 K \u00b7 C \u00b7 I \u00b7 J \u00b7 A</div>
  </td></tr>

  <tr><td class="px" style="padding:6px 28px 4px 28px;text-align:center;">
    <div class="muted" style="font-family:{_MONO};font-size:10px;color:{_MUTED};letter-spacing:0.1em;">WEEKLY ENERGY DRINK SCAN \u00b7 LT</div>
  </td></tr>

  <tr><td class="px" style="padding:18px 28px 0 28px;">
    <div class="dash" style="font-family:{_MONO};font-size:11px;color:{_DASH};letter-spacing:0.3em;">\u2702 \u2012 \u2012 \u2012 \u2012 \u2012 \u2012 \u2012 \u2012 \u2012 \u2012 \u2012 \u2012 \u2012 \u2012 \u2012 \u2012 \u2012 \u2012 \u2012 \u2012 \u2012 \u2012 \u2012 \u2012 \u2012 \u2012 \u2012 \u2012 \u2012</div>
  </td></tr>

  <tr><td class="px" style="padding:18px 28px 4px 28px;">
    <table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" style="font-family:{_MONO};font-size:11px;">
      <tr>
        <td class="muted" style="color:{_MUTED};padding:2px 0;">DATA</td>
        <td align="right" class="ink" style="color:{_INK};padding:2px 0;font-weight:700;">{h(date_disp)}</td>
      </tr>
      <tr>
        <td class="muted" style="color:{_MUTED};padding:2px 0;">SAVAIT\u0116</td>
        <td align="right" class="ink" style="color:{_INK};padding:2px 0;font-weight:700;">{h(week_lbl)}</td>
      </tr>
      <tr>
        <td class="muted" style="color:{_MUTED};padding:2px 0;">KATEGORIJA</td>
        <td align="right" class="ink" style="color:{_INK};padding:2px 0;font-weight:700;">ENERGETINIAI G\u0116RIMAI</td>
      </tr>
      <tr>
        <td class="muted" style="color:{_MUTED};padding:2px 0;">RADO</td>
        <td align="right" style="padding:2px 0;">
          <span style="background:{_M};color:#fff;font-weight:800;padding:1px 7px;letter-spacing:0.08em;">{h(rado)}</span>
        </td>
      </tr>
    </table>
  </td></tr>

  <tr><td class="px" style="padding:22px 28px 4px 28px;">
    <div class="big-headline ink" style="font-family:{_MONO};font-size:44px;font-weight:800;letter-spacing:-0.03em;color:{_INK};line-height:0.98;">
      Laba diena \u2014<br>
      \u0161tai tavo<br>
      <span style="color:{_M};">energijos&nbsp;kvitas.</span>
    </div>
  </td></tr>

  <tr><td class="px" style="padding:14px 28px 4px 28px;">
    <div class="muted" style="font-family:{_MONO};font-size:11px;color:{_MUTED};line-height:1.6;letter-spacing:0.02em;">
      Suskenavome 7 parduotuves. {h(str(n_stores))} turi k\u0105 pasi\u016blyti.<br>
      Pigiausia banka \u0161i\u0105 savait\u0119: <span class="ink" style="color:{_INK};font-weight:700;">{h(cheapest_line)}</span>.
    </div>
  </td></tr>

  <tr><td class="px" style="padding:22px 28px 10px 28px;">
    <div class="dash" style="font-family:{_MONO};font-size:11px;color:{_DASH};letter-spacing:0.3em;">\u2550 \u2550 \u2550 \u2550 \u2550 \u2550 \u2550 \u2550 \u2550 \u2550 \u2550 \u2550 \u2550 \u2550 \u2550 \u2550 \u2550 \u2550 \u2550 \u2550 \u2550 \u2550 \u2550 \u2550</div>
  </td></tr>

  {store_blocks}

  <tr><td class="px" style="padding:20px 28px 6px 28px;">
    <div class="dash" style="font-family:{_MONO};font-size:11px;color:{_DASH};letter-spacing:0.3em;">\u2550 \u2550 \u2550 \u2550 \u2550 \u2550 \u2550 \u2550 \u2550 \u2550 \u2550 \u2550 \u2550 \u2550 \u2550 \u2550 \u2550 \u2550 \u2550 \u2550 \u2550 \u2550 \u2550 \u2550</div>
  </td></tr>

  <tr><td class="px" style="padding:8px 28px 0 28px;">
    <table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" style="font-family:{_MONO};font-size:12px;">
      <tr>
        <td class="muted" style="color:{_MUTED};padding:3px 0;">PASI\u016eLYM\u0172</td>
        <td align="right" class="ink" style="color:{_INK};font-weight:700;padding:3px 0;">{n_deals}</td>
      </tr>
      <tr>
        <td class="muted" style="color:{_MUTED};padding:3px 0;">DID\u017dIAUSIA NUOLAIDA</td>
        <td align="right" class="ink" style="color:{_INK};font-weight:700;padding:3px 0;">{h(best_disc)}</td>
      </tr>
      <tr>
        <td class="muted" style="color:{_MUTED};padding:3px 0;">PIGIAUSIAS VIENETAS</td>
        <td align="right" style="padding:3px 0;">{cheapest_chip}</td>
      </tr>
    </table>
  </td></tr>

  {cta_rows}

  <tr><td class="px" style="padding:20px 28px 12px 28px;">
    <div class="dash" style="font-family:{_MONO};font-size:11px;color:{_DASH};letter-spacing:0.3em;">\u2702 \u2012 \u2012 \u2012 \u2012 \u2012 \u2012 \u2012 \u2012 \u2012 \u2012 \u2012 \u2012 \u2012 \u2012 \u2012 \u2012 \u2012 \u2012 \u2012 \u2012 \u2012 \u2012 \u2012 \u2012 \u2012 \u2012 \u2012 \u2012 \u2012</div>
  </td></tr>

  <tr><td class="px" style="padding:0 28px 28px 28px;text-align:center;">
    <div class="muted" style="font-family:{_MONO};font-size:10px;color:{_MUTED};line-height:1.7;letter-spacing:0.04em;">
      A\u010ci\u016a \u00b7 THANK YOU \u00b7 GRAZIE<br>
      duomenys i\u0161 <a href="https://www.raskakcija.lt" class="ink" style="color:{_INK};font-weight:700;text-decoration:underline;">raskakcija.lt</a> \u00b7 OCR, gali b\u016bti netikslu
    </div>
  </td></tr>

</table>
</td></tr>
</table>
</body>
</html>"""


def _store_block(idx: int, r: dict) -> str:
    store_name = r["store_name"].upper()
    date_from  = r["dates"]["from"]
    date_to    = r["dates"]["to"]
    matches    = [m for pg in r["pages"] for m in pg["matches"]]

    items_html = ""
    for i, m in enumerate(matches):
        if i > 0:
            items_html += f"""
  <tr><td class="px" style="padding:10px 28px 0 28px;">
    <div class="dash" style="font-family:{_MONO};font-size:11px;color:{_DASH};letter-spacing:0.3em;">\u2012 \u2012 \u2012 \u2012 \u2012 \u2012 \u2012 \u2012 \u2012 \u2012 \u2012 \u2012 \u2012 \u2012 \u2012 \u2012 \u2012 \u2012 \u2012 \u2012 \u2012 \u2012 \u2012 \u2012 \u2012 \u2012 \u2012 \u2012 \u2012 \u2012</div>
  </td></tr>"""
        items_html += _deal_item(m)

    return f"""
  <tr><td class="px" style="padding:6px 28px 0 28px;">
    <table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0">
      <tr>
        <td style="font-family:{_MONO};font-size:10px;letter-spacing:0.14em;color:{_MUTED};">\u203a STORE {idx:02d}</td>
        <td align="right" style="font-family:{_MONO};font-size:10px;color:{_MUTED};letter-spacing:0.1em;">{h(date_from)} \u2192 {h(date_to)}</td>
      </tr>
      <tr>
        <td colspan="2" class="ink" style="font-family:{_MONO};font-size:30px;font-weight:800;letter-spacing:-0.02em;color:{_INK};padding:4px 0 0 0;">{h(store_name)}</td>
      </tr>
    </table>
  </td></tr>

  <tr><td class="px" style="padding:14px 28px 4px 28px;">
    <div class="rule2" style="border-top:1px dashed {_DASH};height:1px;line-height:1px;font-size:0;">&nbsp;</div>
  </td></tr>

  {items_html}

  <tr><td class="px" style="padding:14px 28px 8px 28px;">
    <div class="dash" style="font-family:{_MONO};font-size:11px;color:{_DASH};letter-spacing:0.3em;">\u2012 \u2012 \u2012 \u2012 \u2012 \u2012 \u2012 \u2012 \u2012 \u2012 \u2012 \u2012 \u2012 \u2012 \u2012 \u2012 \u2012 \u2012 \u2012 \u2012 \u2012 \u2012 \u2012 \u2012 \u2012 \u2012 \u2012 \u2012 \u2012 \u2012</div>
  </td></tr>"""


def _deal_item(m: dict) -> str:
    snippet       = m["snippet"][:40].strip()
    price         = m.get("price") or ""
    regular_price = m.get("regular_price") or ""
    pct           = _discount_pct(price, regular_price)

    if price:
        right_label     = "AKCIJOS KAINA"
        right_price_html = f'<div class="big-price" style="font-size:34px;font-weight:800;color:{_M};letter-spacing:-0.02em;line-height:1;">{h(price)}</div>'
        right_sub       = f'<div style="font-size:11px;color:{_INK};font-weight:800;padding-top:4px;" class="ink">SAVE \u2212{pct}%</div>' if pct else ""
    else:
        right_label     = "NUOLAIDA"
        hit             = re.search(r"(\d+)\s*%", m["snippet"])
        disc_str        = f"\u2212{hit.group(1)}%" if hit else "\u2013"
        right_price_html = f'<div class="big-price" style="font-size:34px;font-weight:800;color:{_M};letter-spacing:-0.02em;line-height:1;">{h(disc_str)}</div>'
        right_sub       = ""

    meta_html = (
        f'QTY 1 \u00b7 \u012ePRASTA <span class="strike" style="text-decoration:line-through;color:#b6a9be;">{h(regular_price)}</span>'
        if regular_price else "QTY 1 \u00b7 SKU \u2014"
    )

    return f"""
  <tr><td class="px" style="padding:10px 28px 0 28px;">
    <table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0">
      <tr>
        <td valign="top" style="font-family:{_MONO};">
          <div class="ink" style="font-size:20px;font-weight:800;color:{_INK};letter-spacing:-0.01em;padding-bottom:2px;">{h(snippet)}</div>
          <div class="muted" style="font-size:10px;color:{_MUTED};letter-spacing:0.06em;">{meta_html}</div>
        </td>
        <td valign="top" align="right" style="font-family:{_MONO};white-space:nowrap;">
          <div style="font-size:11px;color:{_M};font-weight:800;letter-spacing:0.06em;padding-bottom:2px;">{right_label}</div>
          {right_price_html}
          {right_sub}
        </td>
      </tr>
    </table>
  </td></tr>"""


def _cta_row(r: dict, idx: int) -> str:
    bg = _M if idx % 2 == 0 else _INK
    top_pad = "22px" if idx == 0 else "6px"
    return f"""
  <tr><td class="px" style="padding:{top_pad} 28px 0 28px;">
    <a href="{h(r['catalog_url'])}" style="display:block;text-align:center;background:{bg};color:#fff;font-family:{_MONO};font-size:11px;font-weight:800;letter-spacing:0.12em;text-transform:uppercase;padding:14px 10px;text-decoration:none;">
      {h(r['store_name'].upper())} katalogas \u2192
    </a>
  </td></tr>"""


# ── plain-text fallback ───────────────────────────────────────────────────────

def _build_plain(store_results: list[dict], today: str) -> str:
    lines = [f"KVITAS // Energetiniai g\u0117rimai akcijoje \u2013 {today}", "=" * 50, ""]
    for r in store_results:
        lines.append(f"{r['store_name'].upper()}  ({r['dates']['from']} \u2013 {r['dates']['to']})")
        lines.append("-" * 40)
        for page in r["pages"]:
            for m in page["matches"]:
                price_str = m["price"] or ""
                if m["regular_price"]:
                    price_str += f"  (buvo {m['regular_price']})"
                lines.append(f"\u2022 {m['snippet'][:100].strip()}  {price_str}")
        lines.append("")
    lines += ["=" * 50, "Duomenys i\u0161 raskakcija.lt \u00b7 OCR, gali b\u016bti netikslu"]
    return "\n".join(lines)
