from __future__ import annotations
from pydantic import BaseModel, Field

class RefundMatch(BaseModel):
    """A refund linked to its most likely original charge."""

    refund_date: str
    refund_amount: float
    refund_description: str
    original_date: str
    original_amount: float
    original_description: str
    match_confidence: str  # "high", "medium", "low"


class MissingReceipt(BaseModel):
    """A CC charge above threshold with no matching receipt."""

    date: str
    description: str
    amount: float
    category: str


class OverdueInvoice(BaseModel):
    """An outstanding invoice with aging info."""

    client: str
    amount: float
    date_sent: str
    days_outstanding: int
    urgency: str  # "overdue", "due_soon", "recent"


class ExpenseAnomaly(BaseModel):
    """A charge significantly different from the usual for that merchant."""

    date: str
    description: str
    amount: float
    usual_amount: float
    deviation_pct: float


class TaxSummary(BaseModel):
    """Deductible vs non-deductible expense breakdown."""

    total_deductible: float
    total_non_deductible: float
    deductible_by_category: dict[str, float] = Field(default_factory=dict)
    refunds_total: float
    net_deductible: float


class DataQuality(BaseModel):
    """How clean and complete is this shoebox."""

    score: float  # 0-100
    issues: list[str] = Field(default_factory=list)
    recommendations: list[str] = Field(default_factory=list)


class ReconciliationResult(BaseModel):
    """Everything the reconciliation engine found."""

    job_id: str
    refund_matches: list[RefundMatch] = Field(default_factory=list)
    missing_receipts: list[MissingReceipt] = Field(default_factory=list)
    overdue_invoices: list[OverdueInvoice] = Field(default_factory=list)
    anomalies: list[ExpenseAnomaly] = Field(default_factory=list)
    tax_summary: TaxSummary | None = None
    data_quality: DataQuality | None = None
    insights: list[str] = Field(default_factory=list)


