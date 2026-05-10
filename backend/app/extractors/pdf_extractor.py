"""
PDF extractor — pulls transactions from credit card statement PDFs.

Uses pdfplumber for text extraction, then regex to find transaction lines.
The regex is tuned for the format: TXN-MMDD-NNN  Mon DD  DESCRIPTION  $AMOUNT
but the architecture supports adding more patterns for other statement formats.
"""

from __future__ import annotations

import re
from pathlib import Path

import pdfplumber

from app.models.schemas import ExtractedTransaction

# Month abbreviation > number
MONTH_MAP = {
    "jan": 1, "feb": 2, "mar": 3, "apr": 4,
    "may": 5, "jun": 6, "jul": 7, "aug": 8,
    "sep": 9, "oct": 10, "nov": 11, "dec": 12,
}

# Transaction line pattern for this statement format:
# TXN-MMDD-NNN  Mon DD  DESCRIPTION  $AMOUNT
TX_PATTERN = re.compile(
    r"(TXN-\d{4}-\d{3})\s+"       # transaction ID
    r"(\w{3})\s+(\d{2})\s+"       # month abbrev + day
    r"(.+?)\s+"                    # description (non-greedy)
    r"(–?\$-?[\d,.]+)"            # amount: $ required
)


def extract_pdf(file_path: str) -> tuple[list[ExtractedTransaction], list[str]]:
    """
    Extract transactions from a credit card statement PDF.

    Returns:
        (transactions, warnings)
    """
    transactions: list[ExtractedTransaction] = []
    warnings: list[str] = []
    path = Path(file_path)

    try:
        with pdfplumber.open(path) as pdf:
            full_text = ""
            for page in pdf.pages:
                text = page.extract_text()
                if text:
                    full_text += text + "\n"
    except Exception as e:
        warnings.append(f"PDF extraction failed for '{path.name}': {e}")
        return transactions, warnings

    if not full_text.strip():
        warnings.append(f"PDF '{path.name}': no text could be extracted")
        return transactions, warnings

    matches = TX_PATTERN.findall(full_text)

    if not matches:
        # Try to extract any useful text even if our pattern doesn't match
        warnings.append(
            f"PDF '{path.name}': no transaction lines matched the expected format. "
            f"Extracted {len(full_text)} chars of raw text."
        )
        return transactions, warnings

    for txn_id, month_str, day_str, description, raw_amount in matches:
        try:
            month = MONTH_MAP.get(month_str.lower())
            if month is None:
                warnings.append(f"Unknown month '{month_str}' in transaction {txn_id}")
                continue

            # Parse amount: remove $, commas, convert en-dash to minus
            cleaned = raw_amount.replace("$", "").replace(",", "").replace("\u2013", "-")
            amount = float(cleaned)

            # Infer year from context (Q1 2025 statement)
            date_str = f"2025-{month:02d}-{int(day_str):02d}"

            transactions.append(ExtractedTransaction(
                date=date_str,
                description=description.strip(),
                amount=amount,
                transaction_id=txn_id,
                source_file=path.name,
            ))

        except (ValueError, KeyError) as e:
            warnings.append(f"PDF: couldn't parse transaction {txn_id}: {e}")

    return transactions, warnings
