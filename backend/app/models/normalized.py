"""
Normalized financial models.

These are the clean, structured records that come out of the normalize step.
"""

from __future__ import annotations

import enum
from pydantic import BaseModel, Field


class ExpenseCategory(str, enum.Enum):
    SOFTWARE = "Software & Subscriptions"
    OFFICE_SUPPLIES = "Office Supplies"
    SHIPPING = "Shipping & Postage"
    MEALS = "Meals & Entertainment"
    TRANSPORT = "Transportation"
    COWORKING = "Coworking"
    HOSTING = "Hosting & Domains"
    PERSONAL = "Personal (Non-Deductible)"
    OTHER = "Other"


class InvoiceStatus(str, enum.Enum):
    PAID = "Paid"
    OUTSTANDING = "Outstanding"


class NormalizedExpense(BaseModel):
    """A clean, categorized expense record."""

    date: str
    description: str
    amount: float
    category: ExpenseCategory
    source: str  # "credit_card", "cash_receipt"
    is_personal: bool = False
    is_duplicate: bool = False
    is_refund: bool = False
    tax_deductible: bool = True
    flags: list[str] = Field(default_factory=list)
    transaction_id: str = ""
    source_file: str = ""


class NormalizedInvoice(BaseModel):
    """A clean invoice with computed payment speed."""

    client: str
    description: str
    amount: float
    date_sent: str | None = None
    date_paid: str | None = None
    status: InvoiceStatus
    days_to_payment: int | None = None
    source_file: str = ""


class NormalizedReceipt(BaseModel):
    """A normalized receipt from OCR extraction."""

    vendor: str
    date: str
    total: float
    items: list[dict] = Field(default_factory=list)
    payment_method: str = "Unknown"
    confidence: float = 0.0
    source_file: str = ""
    is_valid: bool = True


class ActionItem(BaseModel):
    """A task extracted from notes."""

    description: str
    done: bool
    category: str  # follow-up, admin, tax, opportunity


class NormalizedResult(BaseModel):
    """The full normalized output for a job."""

    job_id: str
    expenses: list[NormalizedExpense] = Field(default_factory=list)
    invoices: list[NormalizedInvoice] = Field(default_factory=list)
    receipts: list[NormalizedReceipt] = Field(default_factory=list)
    action_items: list[ActionItem] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    totals: dict = Field(default_factory=dict)
