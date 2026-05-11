"""
Reconciliation engine — the core of Tablo.

This is what makes Tablo different from a parser. It reads documents
*against each other* and flags what an accountant would catch:

1. Refund matching — links refunds to their original charges
2. Missing receipt detection — CC charges without documentation
3. Invoice aging — how overdue are outstanding invoices
4. Expense anomalies — charges significantly higher than usual
5. Tax summary — deductible vs non-deductible breakdown
6. Data quality score — how clean/complete is this shoebox

The normalizer handles per-record intelligence (categories, duplicates,
personal flags). The reconciler handles cross-record intelligence.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import date

from pydantic import BaseModel, Field

from app.models.normalized import (
    InvoiceStatus,
    NormalizedExpense,
    NormalizedInvoice,
    NormalizedResult,
)

from app.models.reconciliation import (
    RefundMatch,
    MissingReceipt,
    OverdueInvoice,
    ExpenseAnomaly,
    TaxSummary,
    DataQuality,
    ReconciliationResult,
)

# Storage
_results: dict[str, ReconciliationResult] = {}


def get_reconciliation(job_id: str) -> ReconciliationResult | None:
    return _results.get(job_id)


def reconcile(normalized: NormalizedResult) -> ReconciliationResult:
    """
    Run cross-document reconciliation on normalized data.

    This is where the AI accountant earns its keep.
    """
    result = ReconciliationResult(job_id=normalized.job_id)

    result.refund_matches = _match_refunds(normalized.expenses)
    result.missing_receipts = _find_missing_receipts(normalized.expenses)
    result.overdue_invoices = _check_overdue(normalized.invoices)
    result.anomalies = _detect_anomalies(normalized.expenses)
    result.tax_summary = _compute_tax_summary(normalized.expenses)
    result.data_quality = _assess_quality(normalized)
    result.insights = _generate_insights(normalized, result)

    _results[normalized.job_id] = result
    return result


#  Refund matching 


def _match_refunds(expenses: list[NormalizedExpense]) -> list[RefundMatch]:
    """
    Link each refund to its most likely original charge.

    Strategy: match by merchant name, then prefer the charge closest
    in time before the refund. If amounts match exactly, high confidence.
    """
    matches: list[RefundMatch] = []

    refunds = [e for e in expenses if e.is_refund]
    charges = [e for e in expenses if not e.is_refund and not e.is_duplicate]

    for refund in refunds:
        refund_merchant = refund.description.split("*")[0].split("#")[0].strip()

        # Find charges with matching merchant
        candidates = []
        for charge in charges:
            charge_merchant = charge.description.split("*")[0].split("#")[0].strip()
            if refund_merchant.lower() == charge_merchant.lower():
                candidates.append(charge)

        if not candidates:
            continue

        # Prefer: exact amount match > closest date before refund
        best = None
        confidence = "low"

        for c in candidates:
            if abs(c.amount) == abs(refund.amount) and c.date <= refund.date:
                best = c
                confidence = "high"
                break

        if best is None:
            # Pick closest date before refund
            before = [c for c in candidates if c.date <= refund.date]
            if before:
                best = max(before, key=lambda c: c.date)
                confidence = "medium"
            else:
                best = candidates[0]
                confidence = "low"

        matches.append(RefundMatch(
            refund_date=refund.date,
            refund_amount=refund.amount,
            refund_description=refund.description,
            original_date=best.date,
            original_amount=best.amount,
            original_description=best.description,
            match_confidence=confidence,
        ))

    return matches


#  Missing receipts 

RECEIPT_THRESHOLD = 25.0  # Flag CC charges above this without receipt


def _find_missing_receipts(expenses: list[NormalizedExpense]) -> list[MissingReceipt]:
    """
    Find CC charges above threshold that don't have matching receipt documentation.

    In Canada, CRA requires receipts for business expenses. This flags
    charges that might need documentation.
    """
    cc_charges = [
        e for e in expenses
        if e.source == "credit_card"
        and not e.is_personal
        and not e.is_duplicate
        and not e.is_refund
        and e.amount >= RECEIPT_THRESHOLD
    ]

    cash_dates_amounts = {
        (e.date, round(e.amount, 2))
        for e in expenses
        if e.source == "cash_receipt"
    }

    missing: list[MissingReceipt] = []
    for charge in cc_charges:
        # Check if there's a matching receipt (by date and similar amount)
        has_receipt = (charge.date, round(charge.amount, 2)) in cash_dates_amounts

        if not has_receipt:
            missing.append(MissingReceipt(
                date=charge.date,
                description=charge.description,
                amount=charge.amount,
                category=charge.category.value,
            ))

    return missing


#  Overdue invoices 


def _check_overdue(invoices: list[NormalizedInvoice]) -> list[OverdueInvoice]:
    """Check outstanding invoices for aging."""
    overdue: list[OverdueInvoice] = []
    today = date.today()

    for inv in invoices:
        if inv.status != InvoiceStatus.OUTSTANDING:
            continue

        if not inv.date_sent:
            continue

        try:
            sent = date.fromisoformat(inv.date_sent)
        except ValueError:
            continue

        days = (today - sent).days
        urgency = "overdue" if days > 30 else "due_soon" if days > 14 else "recent"

        overdue.append(OverdueInvoice(
            client=inv.client,
            amount=inv.amount,
            date_sent=inv.date_sent,
            days_outstanding=days,
            urgency=urgency,
        ))

    return sorted(overdue, key=lambda o: o.days_outstanding, reverse=True)


#  Anomaly detection 


def _detect_anomalies(expenses: list[NormalizedExpense]) -> list[ExpenseAnomaly]:
    """
    Find charges significantly different from the usual for that merchant.

    Groups by merchant keyword, computes average, flags outliers.
    """
    anomalies: list[ExpenseAnomaly] = []

    # Group charges by normalized merchant
    merchant_groups: dict[str, list[NormalizedExpense]] = defaultdict(list)
    for e in expenses:
        if e.is_duplicate or e.is_refund or e.is_personal:
            continue
        key = e.description.split("*")[0].split("#")[0].strip().upper()
        if key:
            merchant_groups[key].append(e)

    for merchant, group in merchant_groups.items():
        if len(group) < 2:
            continue

        amounts = [e.amount for e in group]
        avg = sum(amounts) / len(amounts)

        if avg == 0:
            continue

        for e in group:
            deviation = abs(e.amount - avg) / avg
            if deviation > 0.3 and abs(e.amount - avg) > 10:
                anomalies.append(ExpenseAnomaly(
                    date=e.date,
                    description=e.description,
                    amount=e.amount,
                    usual_amount=round(avg, 2),
                    deviation_pct=round(deviation * 100, 1),
                ))

    return anomalies


#  Tax summary 


def _compute_tax_summary(expenses: list[NormalizedExpense]) -> TaxSummary:
    """Compute deductible vs non-deductible expense breakdown."""
    deductible = [e for e in expenses if e.tax_deductible and not e.is_duplicate and not e.is_refund]
    non_deductible = [e for e in expenses if not e.tax_deductible and not e.is_duplicate]
    refunds = [e for e in expenses if e.is_refund]

    by_category: dict[str, float] = {}
    for e in deductible:
        cat = e.category.value
        by_category[cat] = by_category.get(cat, 0) + round(e.amount, 2)

    total_deductible = sum(e.amount for e in deductible)
    total_refunds = sum(abs(e.amount) for e in refunds)

    return TaxSummary(
        total_deductible=round(total_deductible, 2),
        total_non_deductible=round(sum(e.amount for e in non_deductible), 2),
        deductible_by_category=by_category,
        refunds_total=round(total_refunds, 2),
        net_deductible=round(total_deductible - total_refunds, 2),
    )


#  Data quality score 


def _assess_quality(normalized: NormalizedResult) -> DataQuality:
    """
    Score the completeness and cleanliness of the shoebox data.

    100 = perfect books. Real shoeboxes score 40-70.
    """
    issues: list[str] = []
    recommendations: list[str] = []
    score = 100.0

    # Check for duplicates
    dup_count = sum(1 for e in normalized.expenses if e.is_duplicate)
    if dup_count:
        score -= min(dup_count * 5, 15)
        issues.append(f"{dup_count} duplicate transaction(s) detected")
        recommendations.append("Review flagged duplicates and dispute with your bank if confirmed")

    # Check for personal charges on business card
    personal_count = sum(1 for e in normalized.expenses if e.is_personal)
    if personal_count:
        score -= min(personal_count * 3, 12)
        issues.append(f"{personal_count} personal charge(s) on business card")
        recommendations.append("Move personal subscriptions to a personal card")

    # Check for missing receipts
    cc_no_receipt = sum(
        1 for e in normalized.expenses
        if e.source == "credit_card" and not e.is_personal
        and not e.is_duplicate and not e.is_refund and e.amount >= RECEIPT_THRESHOLD
    )
    if cc_no_receipt > 5:
        score -= 10
        issues.append(f"{cc_no_receipt} business charges over ${RECEIPT_THRESHOLD:.0f} without receipts")
        recommendations.append("Keep receipts for all business expenses over $25 for CRA compliance")

    # Check for outstanding invoices
    outstanding = sum(1 for i in normalized.invoices if i.status == InvoiceStatus.OUTSTANDING)
    if outstanding:
        score -= outstanding * 5
        issues.append(f"{outstanding} outstanding invoice(s)")
        recommendations.append("Follow up on unpaid invoices promptly")

    # Check for uncategorized expenses
    uncategorized = sum(1 for e in normalized.expenses if e.category.value == "Other" and not e.is_duplicate)
    if uncategorized > 3:
        score -= 5
        issues.append(f"{uncategorized} expense(s) could not be categorized")
        recommendations.append("Add merchant rules for unrecognized vendors")

    # Check for receipt quality
    low_confidence = sum(1 for r in normalized.receipts if r.confidence < 0.5 and r.is_valid)
    if low_confidence:
        score -= low_confidence * 3
        issues.append(f"{low_confidence} receipt(s) with low OCR confidence")
        recommendations.append("Use clearer photos or printed receipts when possible")

    # Bonus for good practices
    if normalized.action_items:
        score = min(score + 5, 100)

    score = max(score, 0)

    return DataQuality(
        score=round(score, 1),
        issues=issues,
        recommendations=recommendations,
    )


#  Insights 


def _generate_insights(
    normalized: NormalizedResult,
    reconciliation: ReconciliationResult,
) -> list[str]:
    """Generate human-readable insights from the reconciliation."""
    insights: list[str] = []
    totals = normalized.totals

    # Revenue insight
    gross = totals.get("gross_revenue", 0)
    outstanding = totals.get("outstanding_revenue", 0)
    if gross > 0:
        insights.append(
            f"Q1 revenue: ${gross:,.2f} collected, ${outstanding:,.2f} outstanding"
        )

    # Expense insight
    net = totals.get("net_expenses", 0)
    if net > 0 and gross > 0:
        margin = ((gross - net) / gross) * 100
        insights.append(
            f"Operating margin: {margin:.0f}% (${gross - net:,.2f} net of ${net:,.2f} expenses)"
        )

    # Payment speed
    avg_days = totals.get("avg_payment_days", 0)
    if avg_days > 0:
        insights.append(f"Clients pay in {avg_days} days on average")

    # Top expense category
    by_cat = totals.get("expenses_by_category", {})
    if by_cat:
        top_cat = max(by_cat, key=by_cat.get)
        insights.append(
            f"Biggest expense category: {top_cat} (${by_cat[top_cat]:,.2f})"
        )

    # Top client
    by_client = totals.get("revenue_by_client", {})
    if by_client:
        top_client = max(by_client, key=by_client.get)
        pct = (by_client[top_client] / (gross + outstanding)) * 100 if (gross + outstanding) > 0 else 0
        insights.append(
            f"Top client: {top_client} ({pct:.0f}% of revenue)"
        )

    # Refund insight
    if reconciliation.refund_matches:
        total_refunded = sum(abs(r.refund_amount) for r in reconciliation.refund_matches)
        insights.append(
            f"${total_refunded:,.2f} in refunds received and matched to original charges"
        )

    # Overdue insight
    if reconciliation.overdue_invoices:
        total_overdue = sum(o.amount for o in reconciliation.overdue_invoices)
        insights.append(
            f"${total_overdue:,.2f} in outstanding invoices need follow-up"
        )

    # Anomaly insight
    if reconciliation.anomalies:
        insights.append(
            f"{len(reconciliation.anomalies)} expense amount(s) differ from the usual — worth reviewing"
        )

    return insights
