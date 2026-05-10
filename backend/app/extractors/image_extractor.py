"""
Image extractor — uses Tesseract OCR to read receipt images.

Handles printed receipts well. Handwritten receipts and crumpled photos
will have lower confidence — we report the confidence score so the
reconciliation layer can flag uncertain extractions.
"""

from __future__ import annotations

import re
from pathlib import Path

from PIL import Image, ImageEnhance, ImageFilter
import pytesseract

from app.models.schemas import ExtractedReceipt


# Regex patterns for common receipt fields
AMOUNT_PATTERN = re.compile(r"\$\s?(\d+[.,]\d{2})")
DATE_PATTERNS = [
    re.compile(r"(\d{2}/\d{2}/\d{4})"),      # DD/MM/YYYY or MM/DD/YYYY
    re.compile(r"(\d{4}-\d{2}-\d{2})"),       # ISO
    re.compile(r"(\d{2}-\d{2}-\d{4})"),       # DD-MM-YYYY
]
TOTAL_PATTERNS = [
    re.compile(r"(?:TOTAL|Total|total)[:\s]*\$?\s?(\d+[.,]\d{2})"),
    re.compile(r"(?:MONTANT|Montant)[:\s]*\$?\s?(\d+[.,]\d{2})"),
]


def _preprocess_image(image: Image.Image) -> Image.Image:
    """
    Preprocess a receipt image for better OCR results.

    Converts to grayscale, boosts contrast, and sharpens.
    These steps help Tesseract especially with phone photos.
    """
    # Convert to grayscale
    img = image.convert("L")

    # Boost contrast
    enhancer = ImageEnhance.Contrast(img)
    img = enhancer.enhance(1.8)

    # Sharpen
    img = img.filter(ImageFilter.SHARPEN)

    return img


def _extract_amounts(text: str) -> list[dict]:
    """Pull all dollar amounts from OCR text as line items."""
    items = []
    lines = text.split("\n")

    for line in lines:
        line = line.strip()
        if not line:
            continue

        amounts = AMOUNT_PATTERN.findall(line)
        if amounts:
            # Use the line text minus the amount as the description
            desc = AMOUNT_PATTERN.sub("", line).strip().strip("$").strip()
            for amt_str in amounts:
                try:
                    amt = float(amt_str.replace(",", "."))
                    items.append({"text": desc or "(item)", "amount": amt})
                except ValueError:
                    pass

    return items


def _extract_date(text: str) -> str:
    """Find the first date-like pattern in OCR text."""
    for pattern in DATE_PATTERNS:
        match = pattern.search(text)
        if match:
            return match.group(1)
    return ""


def _extract_total(text: str) -> float | None:
    """Find a TOTAL line in OCR text."""
    for pattern in TOTAL_PATTERNS:
        match = pattern.search(text)
        if match:
            try:
                return float(match.group(1).replace(",", "."))
            except ValueError:
                pass
    return None


def _extract_vendor(text: str) -> str:
    """
    Best-effort vendor extraction: usually the first non-empty line.

    Real receipts typically have the store name at the very top.
    """
    for line in text.split("\n"):
        line = line.strip()
        # Skip very short lines (often just symbols or whitespace artifacts)
        if len(line) > 2 and not line.startswith("*"):
            return line
    return ""


def _compute_confidence(text: str, data: dict) -> float:
    """
    Estimate extraction confidence based on what we found.

    A receipt with a clear vendor, date, and total = high confidence.
    OCR gibberish with no structure = low confidence.
    """
    score = 0.0

    if data.get("vendor"):
        score += 0.25
    if data.get("date"):
        score += 0.25
    if data.get("total") is not None:
        score += 0.3
    if data.get("items"):
        score += 0.2

    # Penalize very short text (likely a bad OCR read)
    if len(text.strip()) < 20:
        score *= 0.5

    return min(score, 1.0)


def extract_image(file_path: str) -> tuple[ExtractedReceipt, list[str]]:
    """
    Extract receipt data from an image using Tesseract OCR.

    Returns:
        (receipt, warnings)
    """
    warnings: list[str] = []
    path = Path(file_path)

    try:
        image = Image.open(path)
    except Exception as e:
        warnings.append(f"Image: couldn't open '{path.name}': {e}")
        return ExtractedReceipt(source_file=path.name), warnings

    # Preprocess for better OCR
    processed = _preprocess_image(image)

    # Run OCR — use both English and French
    try:
        raw_text = pytesseract.image_to_string(
            processed,
            lang="eng+fra",
            config="--psm 6",  # Assume uniform block of text
        )
    except Exception as e:
        warnings.append(f"OCR failed for '{path.name}': {e}")
        # Try with just English
        try:
            raw_text = pytesseract.image_to_string(processed, lang="eng")
        except Exception as e2:
            warnings.append(f"OCR retry also failed for '{path.name}': {e2}")
            return ExtractedReceipt(source_file=path.name), warnings

    if not raw_text.strip():
        warnings.append(
            f"Image '{path.name}': OCR produced no text (may not be a receipt)")
        return ExtractedReceipt(
            raw_text="",
            source_file=path.name,
            confidence=0.0,
        ), warnings

    # Extract structured fields
    vendor = _extract_vendor(raw_text)
    date_str = _extract_date(raw_text)
    total = _extract_total(raw_text)
    items = _extract_amounts(raw_text)

    data = {"vendor": vendor, "date": date_str, "total": total, "items": items}
    confidence = _compute_confidence(raw_text, data)

    if confidence < 0.2:
        warnings.append(
            f"Image '{path.name}': low OCR confidence ({confidence:.0%}). "
            f"File may not be a receipt."
        )

    receipt = ExtractedReceipt(
        vendor=vendor,
        date=date_str,
        items=items,
        total=total,
        raw_text=raw_text,
        confidence=confidence,
        source_file=path.name,
    )

    return receipt, warnings
