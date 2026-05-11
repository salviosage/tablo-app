"""
Normalizer — transforms raw extraction output into clean, structured data.

This is the bridge between extraction (raw) and reconciliation (smart).
It handles:
- Category inference from merchant names
- Personal charge detection from notes
- Duplicate detection via transaction IDs
- Invoice status and payment speed calculation
- Receipt validation and total correction
- Action item extraction from notes
- Totals computation
"""

from __future__ import annotations

import re
from collections import Counter
from datetime import date

from app.models.schemas import ExtractionResult
from app.models.normalized import (
    ActionItem,
    ExpenseCategory,
    InvoiceStatus,
    NormalizedExpense,
    NormalizedInvoice,
    NormalizedReceipt,
    NormalizedResult,
)
from app.services.categorizer import categorize


# Merchants flagged as personal in notes 
DEFAULT_PERSONAL_KEYWORDS = {"netflix", "petco"}


def _normalize_date(raw: str) -> str:
    """
    Normalize a date string to ISO format (YYYY-MM-DD).

    Handles DD/MM/YYYY, MM/DD/YYYY (ambiguous — assumes DD/MM for values > 12),
    and passes through already-ISO dates.
    """
    if not raw:
        return raw

    # Already ISO
    if re.match(r"^\d{4}-\d{2}-\d{2}$", raw):
        return raw

    # DD/MM/YYYY or MM/DD/YYYY
    m = re.match(r"^(\d{2})/(\d{2})/(\d{4})$", raw)
    if m:
        a, b, year = int(m.group(1)), int(m.group(2)), m.group(3)
        # If first number > 12, it must be day (DD/MM/YYYY — common in QC/France)
        if a > 12:
            return f"{year}-{b:02d}-{a:02d}"
        elif b > 12:
            return f"{year}-{a:02d}-{b:02d}"
        else:
            # Ambiguous — assume DD/MM for Montréal context
            return f"{year}-{b:02d}-{a:02d}"

    return raw

# Store normalized results
_results: dict[str, NormalizedResult] = {}


def get_normalized(job_id: str) -> NormalizedResult | None:
    return _results.get(job_id)


def normalize(extraction: ExtractionResult) -> NormalizedResult:
    """
    Normalize an extraction result into clean financial data.

    """
    result = NormalizedResult(job_id=extraction.job_id)
    result.warnings = list(extraction.warnings)

    # Parse notes first — we need personal charge keywords
    personal_keywords = set(DEFAULT_PERSONAL_KEYWORDS)
    for notes in extraction.notes:
        items, extra_keywords = _parse_notes(notes.lines)
        result.action_items.extend(items)
        personal_keywords.update(extra_keywords)

    # Normalize transactions > expenses
    expenses = _normalize_transactions(
        extraction.transactions, personal_keywords, result.warnings
    )
    result.expenses.extend(expenses)

    # Normalize receipts > expenses + receipt records
    receipt_expenses, receipts = _normalize_receipts(
        extraction.receipts, result.warnings
    )
    result.expenses.extend(receipt_expenses)
    result.receipts = receipts

    # Sort expenses by date
    result.expenses.sort(key=lambda e: e.date)

    # Normalize invoices
    result.invoices = _normalize_invoices(extraction.invoices, result.warnings)

    # Compute totals
    result.totals = _compute_totals(result)

    _results[extraction.job_id] = result
    return result


#  Transaction normalization 


def _normalize_transactions(
    transactions: list,
    personal_keywords: set[str],
    warnings: list[str],
) -> list[NormalizedExpense]:
    """Convert raw transactions to normalized expenses with categories and flags."""
    expenses: list[NormalizedExpense] = []

    for txn in transactions:
        category = categorize(txn.description)
        is_personal = _is_personal(txn.description, personal_keywords)
        is_refund = txn.amount < 0

        flags: list[str] = []
        if is_personal:
            flags.append("Personal charge (see notes)")
            category = ExpenseCategory.PERSONAL
        if is_refund:
            flags.append("Refund")

        expenses.append(NormalizedExpense(
            date=txn.date,
            description=txn.description,
            amount=txn.amount,
            category=category,
            source="credit_card",
            is_personal=is_personal,
            is_refund=is_refund,
            tax_deductible=not is_personal,
            flags=flags,
            transaction_id=txn.transaction_id,
            source_file=txn.source_file,
        ))

    # Detect duplicates
    _flag_duplicates(expenses, warnings)

    return expenses


def _is_personal(description: str, keywords: set[str]) -> bool:
    """Check if a charge matches any personal-charge keywords from notes."""
    desc_lower = description.lower()
    return any(kw in desc_lower for kw in keywords)


def _flag_duplicates(expenses: list[NormalizedExpense], warnings: list[str]) -> None:
    """Flag duplicate transactions based on transaction ID."""
    id_counts = Counter(
        e.transaction_id for e in expenses if e.transaction_id
    )

    seen: dict[str, int] = {}
    dup_count = 0

    for expense in expenses:
        tid = expense.transaction_id
        if not tid or id_counts[tid] <= 1:
            continue

        seen[tid] = seen.get(tid, 0) + 1
        if seen[tid] > 1:
            expense.is_duplicate = True
            expense.flags.append(
                f"Possible duplicate ({tid} appears {id_counts[tid]}x)"
            )
            dup_count += 1

    if dup_count:
        warnings.append(
            f"Duplicates: {dup_count} transaction(s) with repeated IDs detected"
        )


#  Receipt normalization 


def _normalize_receipts(
    raw_receipts: list,
    warnings: list[str],
) -> tuple[list[NormalizedExpense], list[NormalizedReceipt]]:
    """Convert OCR receipt data into expenses and clean receipt records."""
    expenses: list[NormalizedExpense] = []
    receipts: list[NormalizedReceipt] = []

    for raw in raw_receipts:
        # Determine if this is a valid receipt
        is_valid = raw.confidence >= 0.2 and (raw.total is not None or len(raw.items) > 0)

        # Fix total: use the TOTAL line from items if available,
        # otherwise use the extracted total
        total = raw.total or 0.0
        if raw.items:
            # Look for a TOTAL item
            for item in raw.items:
                if "total" in item.get("text", "").lower():
                    total = item["amount"]
                    break

        # Detect payment method from OCR text
        payment = "Unknown"
        text_lower = raw.raw_text.lower()
        if "comptant" in text_lower or "cash" in text_lower:
            payment = "Cash"
        elif "e-transfer" in text_lower or "transfert" in text_lower:
            payment = "E-Transfer"
        elif "visa" in text_lower or "mastercard" in text_lower or "debit" in text_lower:
            payment = "Card"

        normalized_date = _normalize_date(raw.date)

        receipt = NormalizedReceipt(
            vendor=raw.vendor,
            date=normalized_date,
            total=total,
            items=[i for i in raw.items if "total" not in i.get("text", "").lower()
                   and "comptant" not in i.get("text", "").lower()
                   and "monnaie" not in i.get("text", "").lower()
                   and "sous-total" not in i.get("text", "").lower()
                   and "tps" not in i.get("text", "").lower()
                   and "tvq" not in i.get("text", "").lower()],
            payment_method=payment,
            confidence=raw.confidence,
            source_file=raw.source_file,
            is_valid=is_valid,
        )
        receipts.append(receipt)

        if not is_valid:
            warnings.append(
                f"Receipt '{raw.source_file}': low confidence ({raw.confidence:.0%}), "
                f"may not be a valid receipt"
            )
            continue

        if total > 0:
            category = categorize(raw.vendor)
            expenses.append(NormalizedExpense(
                date=normalized_date,
                description=f"{raw.vendor}" if raw.vendor else raw.source_file,
                amount=total,
                category=category,
                source="cash_receipt",
                source_file=raw.source_file,
            ))

    return expenses, receipts


#  Invoice normalization 


def _normalize_invoices(
    raw_invoices: list,
    warnings: list[str],
) -> list[NormalizedInvoice]:
    """Convert raw invoices to normalized invoices with status and payment speed."""
    invoices: list[NormalizedInvoice] = []

    for raw in raw_invoices:
        has_paid = raw.date_paid is not None and raw.date_paid != ""
        status = InvoiceStatus.PAID if has_paid else InvoiceStatus.OUTSTANDING

        days = None
        if has_paid and raw.date_sent:
            try:
                sent = date.fromisoformat(raw.date_sent)
                paid = date.fromisoformat(raw.date_paid)
                days = (paid - sent).days
            except (ValueError, TypeError):
                pass

        invoices.append(NormalizedInvoice(
            client=raw.client,
            description=raw.description,
            amount=raw.amount,
            date_sent=raw.date_sent,
            date_paid=raw.date_paid if has_paid else None,
            status=status,
            days_to_payment=days,
            source_file=raw.source_file,
        ))

    return invoices


#  Notes parsing 


def _parse_notes(lines: list[str]) -> tuple[list[ActionItem], set[str]]:
    """
    Parse note lines into action items and extract personal charge keywords.

    Returns:
        (action_items, personal_keywords)
    """
    items: list[ActionItem] = []
    personal_keywords: set[str] = set()

    for line in lines:
        stripped = line.strip()
        if not stripped or stripped.startswith("=="):
            continue

        lower = stripped.lower()

        # [todo] / [done] items
        if lower.startswith("[todo]"):
            desc = stripped[6:].strip().lstrip("—-").strip()
            items.append(ActionItem(
                description=desc,
                done=False,
                category=_categorize_action(desc),
            ))
        elif lower.startswith("[done]"):
            desc = stripped[6:].strip().lstrip("—-").strip()
            items.append(ActionItem(
                description=desc,
                done=True,
                category=_categorize_action(desc),
            ))

        # Personal charge detection: "petco charge was dog food", "netflix is also on this card"
        elif "by accident" in lower or (
            "personal" in lower or "need to move" in lower
        ):
            # Extract merchant name from context
            for kw in ["petco", "netflix", "spotify", "disney"]:
                if kw in lower:
                    personal_keywords.add(kw)

        # Business opportunities
        elif "follow up" in lower and not lower.startswith("["):
            desc = stripped.lstrip("- ").strip()
            items.append(ActionItem(
                description=desc,
                done=False,
                category="opportunity",
            ))

        # Admin reminders
        elif stripped.startswith("- reminder:") or stripped.startswith("- need to"):
            desc = stripped.lstrip("- ").strip()
            items.append(ActionItem(
                description=desc,
                done=False,
                category="admin",
            ))

    return items, personal_keywords


def _categorize_action(text: str) -> str:
    lower = text.lower()
    if any(w in lower for w in ["invoice", "paid", "payment", "outstanding"]):
        return "follow-up"
    if any(w in lower for w in ["tax", "deduction", "registration"]):
        return "tax"
    if any(w in lower for w in ["motion", "signage", "upsell", "q2"]):
        return "opportunity"
    if any(w in lower for w in ["refund", "return", "downgrade"]):
        return "admin"
    return "admin"


#  Totals 


def _compute_totals(result: NormalizedResult) -> dict:
    """Compute summary totals from normalized data."""
    biz = [e for e in result.expenses if not e.is_personal and not e.is_duplicate]
    charges = [e for e in biz if not e.is_refund]
    refunds = [e for e in biz if e.is_refund]

    paid = [i for i in result.invoices if i.status == InvoiceStatus.PAID]
    outstanding = [i for i in result.invoices if i.status == InvoiceStatus.OUTSTANDING]

    gross_revenue = sum(i.amount for i in paid)
    outstanding_revenue = sum(i.amount for i in outstanding)
    total_charges = sum(e.amount for e in charges)
    total_refunds = sum(abs(e.amount) for e in refunds)
    net_expenses = total_charges - total_refunds

    # Card vs cash breakdown
    card_charges = sum(e.amount for e in charges if e.source == "credit_card")
    cash_charges = sum(e.amount for e in charges if e.source == "cash_receipt")

    # By category
    by_category = {}
    for e in charges:
        cat = e.category.value
        by_category[cat] = by_category.get(cat, 0) + round(e.amount, 2)

    # By month
    by_month = {}
    for e in charges:
        month = e.date[:7] if len(e.date) >= 7 else "unknown"
        by_month[month] = by_month.get(month, 0) + round(e.amount, 2)

    # By client
    by_client = {}
    for i in result.invoices:
        by_client[i.client] = by_client.get(i.client, 0) + i.amount

    # Payment speed
    payment_days = [i.days_to_payment for i in paid if i.days_to_payment is not None]
    avg_days = round(sum(payment_days) / len(payment_days), 1) if payment_days else 0

    return {
        "gross_revenue": gross_revenue,
        "outstanding_revenue": outstanding_revenue,
        "total_expenses_card": round(card_charges, 2),
        "total_expenses_cash": round(cash_charges, 2),
        "total_refunds": round(total_refunds, 2),
        "net_expenses": round(net_expenses, 2),
        "net_income": round(gross_revenue - net_expenses, 2),
        "expenses_by_category": by_category,
        "expenses_by_month": by_month,
        "revenue_by_client": by_client,
        "avg_payment_days": avg_days,
        "personal_charges_flagged": len([e for e in result.expenses if e.is_personal]),
        "duplicates_flagged": len([e for e in result.expenses if e.is_duplicate]),
        "invoices_outstanding": len(outstanding),
    }
