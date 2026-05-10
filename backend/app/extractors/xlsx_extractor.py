"""
XLSX extractor — pulls invoice data from spreadsheets.

Handles:
- Multiple date formats (at least 5 in the real data)
- Empty/null rows 
- Flexible column detection via header keywords
- Amount normalization (string or numeric cells)
"""

from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path

import openpyxl

from app.models.schemas import ExtractedInvoice

# Every date format the freelancer might use.
# Ordered from most specific to least.
DATE_FORMATS = [
    "%B %d, %Y",     # "February 15, 2025"
    "%b %d, %Y",     # "Feb 15, 2025"
    "%b %d, %y",     # "Mar 28, 25"
    "%m/%d/%Y",      # "1/5/2025"
    "%m/%d/%y",      # "3/18/25"
    "%Y-%m-%d",      # ISO
]

# Clean up stray dashes and double spaces in date strings
DASH_CLEANUP = re.compile(r"\s*-\s*")


def _parse_date(raw) -> str | None:
    """
    Try every known date format against the raw value.

    Returns ISO date string or None.
    """
    if raw is None:
        return None

    # Handle datetime objects from openpyxl
    if isinstance(raw, datetime):
        return raw.date().isoformat()

    cleaned = str(raw).strip()
    if not cleaned:
        return None

    # Normalize separators
    cleaned = DASH_CLEANUP.sub(" ", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned)

    # Try with added comma: "Jan 30 2025" > "Jan 30, 2025"
    variants = [cleaned]
    match = re.match(r"^(\w+ \d{1,2})\s+(\d{2,4})$", cleaned)
    if match:
        variants.append(f"{match.group(1)}, {match.group(2)}")

    for variant in variants:
        for fmt in DATE_FORMATS:
            try:
                return datetime.strptime(variant, fmt).date().isoformat()
            except ValueError:
                continue

    # Return the raw string so the normalizer can try later
    return cleaned


def _parse_amount(raw) -> float | None:
    """Parse an amount from a cell — could be numeric or a string like '$3,500.00'."""
    if raw is None:
        return None
    if isinstance(raw, (int, float)):
        return float(raw)
    cleaned = str(raw).replace("$", "").replace(",", "").strip()
    try:
        return float(cleaned)
    except ValueError:
        return None


def extract_xlsx(file_path: str) -> tuple[list[ExtractedInvoice], list[str]]:
    """
    Extract invoices from a spreadsheet.

    Returns:
        (invoices, warnings)
    """
    invoices: list[ExtractedInvoice] = []
    warnings: list[str] = []
    path = Path(file_path)

    try:
        wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
    except Exception as e:
        warnings.append(f"XLSX: couldn't open '{path.name}': {e}")
        return invoices, warnings

    ws = wb.active
    rows = list(ws.iter_rows(values_only=True))
    wb.close()

    if not rows:
        warnings.append(f"XLSX '{path.name}': spreadsheet is empty")
        return invoices, warnings

    # Detect columns from headers
    headers = [str(h).strip().lower() if h else "" for h in rows[0]]
    col_map: dict[str, int] = {}

    for i, h in enumerate(headers):
        if "client" in h and "client" not in col_map:
            col_map["client"] = i
        elif ("description" in h or "desc" in h) and "description" not in col_map:
            col_map["description"] = i
        elif "amount" in h and "amount" not in col_map:
            col_map["amount"] = i
        elif "sent" in h and "date_sent" not in col_map:
            col_map["date_sent"] = i
        elif "paid" in h and "date_paid" not in col_map:
            col_map["date_paid"] = i

    required = {"client", "amount"}
    missing = required - set(col_map.keys())
    if missing:
        warnings.append(f"XLSX '{path.name}': missing expected columns: {missing}")
        return invoices, warnings

    # Parse data rows
    empty_count = 0

    for row_idx, row in enumerate(rows[1:], start=2):
        client = row[col_map["client"]] if col_map["client"] < len(row) else None
        if client is None or str(client).strip() == "":
            empty_count += 1
            continue

        amount = _parse_amount(row[col_map["amount"]] if col_map["amount"] < len(row) else None)
        if amount is None:
            warnings.append(f"XLSX row {row_idx}: couldn't parse amount")
            continue

        description = ""
        if "description" in col_map and col_map["description"] < len(row):
            description = str(row[col_map["description"]] or "").strip()

        date_sent = None
        if "date_sent" in col_map and col_map["date_sent"] < len(row):
            date_sent = _parse_date(row[col_map["date_sent"]])

        date_paid = None
        if "date_paid" in col_map and col_map["date_paid"] < len(row):
            date_paid = _parse_date(row[col_map["date_paid"]])

        invoices.append(ExtractedInvoice(
            client=str(client).strip(),
            description=description,
            amount=amount,
            date_sent=date_sent,
            date_paid=date_paid,
            source_file=path.name,
        ))

    if empty_count > 5:
        warnings.append(
            f"XLSX '{path.name}': skipped {empty_count} empty rows "
            f"(found {len(invoices)} actual invoices)"
        )

    return invoices, warnings
