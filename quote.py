"""Quoting pipeline: spec-reader -> pricer -> margin-checker -> doc-writer.

Usage: python quote.py
Reads data/spec.md and data/price_list.csv, writes quote/quote.md and
quote/margin_review.md. Items not on the price list are marked PRICE NEEDED;
no price is ever invented.
"""
import csv
import re
from datetime import date, timedelta
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path

TARGET_MARKUP = Decimal("0.20")  # flag any line whose markup on cost is below 20%
VAT_RATE = Decimal("0.22")
CURRENCY = "EUR"
VALIDITY_DAYS = 30
QUOTE_DATE = date(2026, 10, 7)
PRICE_NEEDED = "PRICE NEEDED"

# Spec wording -> price-list SKU. A spec line with no entry here is unpriced.
SKU_MAP = {
    "steel wall brackets": "BRK-150-GAL",
    "door hinges": "HNG-100-SS",
}

ROOT = Path(__file__).parent


def money(x):
    return x.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def spec_reader(path):
    """Return [(description, qty)] from the spec's scope bullets."""
    items = []
    for line in path.read_text().splitlines():
        m = re.match(r"-\s*Supply\s+(\d+)\s*x\s*(.+)", line)
        if m:
            items.append((m.group(2).strip(), int(m.group(1))))
        elif re.match(r"-\s*Install", line):
            items.append((line.lstrip("- ").strip(), 1))
    return items


def pricer(items, price_list):
    lines = []
    for desc, qty in items:
        sku = next((s for k, s in SKU_MAP.items() if k in desc.lower()), None)
        row = price_list.get(sku)
        if row is None:
            lines.append({"desc": desc, "qty": qty, "sku": None})
            continue
        price, cost = Decimal(row["unit_price"]), Decimal(row["unit_cost"])
        lines.append({
            "desc": row["description"], "qty": qty, "sku": sku, "unit": row["unit"],
            "unit_price": price, "unit_cost": cost,
            "total": money(price * qty), "cost_total": money(cost * qty),
        })
    return lines


def margin_checker(lines):
    for ln in lines:
        if ln["sku"] is None:
            ln["markup"], ln["flag"] = None, PRICE_NEEDED
            continue
        ln["markup"] = (ln["unit_price"] - ln["unit_cost"]) / ln["unit_cost"]
        ln["flag"] = "UNDER TARGET" if ln["markup"] < TARGET_MARKUP else "OK"
    return lines


def doc_writer(lines):
    priced = [ln for ln in lines if ln["sku"]]
    subtotal = money(sum((ln["total"] for ln in priced), Decimal(0)))
    vat = money(subtotal * VAT_RATE)
    total = subtotal + vat
    valid_until = QUOTE_DATE + timedelta(days=VALIDITY_DAYS)
    missing = [ln for ln in lines if ln["sku"] is None]

    out = [
        "# Quotation Q-JS-0001",
        "",
        f"**Customer:** Example Customer Ltd  ",
        f"**Job ref:** JS-0001  ",
        f"**Date:** {QUOTE_DATE.isoformat()}  ",
        f"**Valid until:** {valid_until.isoformat()} ({VALIDITY_DAYS} days)  ",
        f"**Currency:** {CURRENCY}",
        "",
        "| # | SKU | Description | Qty | Unit | Unit price | Line total |",
        "|---|-----|-------------|----:|------|-----------:|-----------:|",
    ]
    for i, ln in enumerate(lines, 1):
        if ln["sku"]:
            out.append(f"| {i} | {ln['sku']} | {ln['desc']} | {ln['qty']} | {ln['unit']} "
                       f"| {ln['unit_price']:.2f} | {ln['total']:.2f} |")
        else:
            out.append(f"| {i} | — | {ln['desc']} | {ln['qty']} | job "
                       f"| **{PRICE_NEEDED}** | **{PRICE_NEEDED}** |")
    out += [
        "",
        f"| | {CURRENCY} |",
        "|---|---:|",
        f"| Subtotal (priced lines) | {subtotal:.2f} |",
        f"| VAT @ {VAT_RATE * 100:.0f}% | {vat:.2f} |",
        f"| **Total** | **{total:.2f}** |",
        "",
    ]
    if missing:
        out.append(f"> **Incomplete quote:** {len(missing)} line(s) marked {PRICE_NEEDED} are "
                   "excluded from the subtotal, VAT and total. Do not issue until priced.")
        out.append("")
    out.append(f"This quotation is valid until {valid_until.isoformat()}. Prices exclude VAT unless stated.")

    review = [
        "# Margin review — Q-JS-0001 (internal, do not send)",
        "",
        f"Target: markup on cost >= {TARGET_MARKUP * 100:.0f}%",
        "",
        "| # | SKU | Qty | Unit cost | Unit price | Markup | Status |",
        "|---|-----|----:|----------:|-----------:|-------:|--------|",
    ]
    for i, ln in enumerate(lines, 1):
        if ln["sku"]:
            review.append(f"| {i} | {ln['sku']} | {ln['qty']} | {ln['unit_cost']:.2f} "
                          f"| {ln['unit_price']:.2f} | {ln['markup'] * 100:.1f}% | {ln['flag']} |")
        else:
            review.append(f"| {i} | — ({ln['desc']}) | {ln['qty']} | — | — | — | {PRICE_NEEDED} |")
    return "\n".join(out) + "\n", "\n".join(review) + "\n"


def main():
    with open(ROOT / "data/price_list.csv", newline="") as f:
        price_list = {r["sku"]: r for r in csv.DictReader(f)}
    items = spec_reader(ROOT / "data/spec.md")
    lines = margin_checker(pricer(items, price_list))
    quote, review = doc_writer(lines)
    (ROOT / "quote").mkdir(exist_ok=True)
    (ROOT / "quote/quote.md").write_text(quote)
    (ROOT / "quote/margin_review.md").write_text(review)
    print(quote)
    print(review)


if __name__ == "__main__":
    main()
