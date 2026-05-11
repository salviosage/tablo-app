"""
Tests for the normalize feature.

Covers: category inference, personal charge detection, duplicate flagging,
invoice status, notes parsing, totals computation, and full pipeline.
"""

import io
from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app
from app.models.normalized import ExpenseCategory, InvoiceStatus
from app.services.categorizer import categorize


SHOEBOX_PATH = Path(__file__).parent.parent.parent / "data" / "shoebox.zip"
if not SHOEBOX_PATH.exists():
    SHOEBOX_PATH = Path("/home/claude/tablo/data/shoebox.zip")


#  Categorizer unit tests 


class TestCategorizer:
    def test_software(self):
        assert categorize("ADOBE *CREATIVE CL") == ExpenseCategory.SOFTWARE
        assert categorize("CANVA.COM") == ExpenseCategory.SOFTWARE
        assert categorize("GOOGLE *WORKSPACE") == ExpenseCategory.SOFTWARE
        assert categorize("SHOPIFY* 1234567") == ExpenseCategory.SOFTWARE

    def test_personal(self):
        assert categorize("NETFLIX.COM") == ExpenseCategory.PERSONAL
        assert categorize("PETCO #4521") == ExpenseCategory.PERSONAL

    def test_office_supplies(self):
        assert categorize("AMAZON.CA *OFFICE") == ExpenseCategory.OFFICE_SUPPLIES
        assert categorize("STAPLES #0312") == ExpenseCategory.OFFICE_SUPPLIES
        assert categorize("BUREAU EN GROS") == ExpenseCategory.OFFICE_SUPPLIES

    def test_shipping(self):
        assert categorize("POSTES CANADA") == ExpenseCategory.SHIPPING

    def test_transport(self):
        assert categorize("WAYMO BUSINESS *X MONTREAL") == ExpenseCategory.TRANSPORT

    def test_coworking(self):
        assert categorize("VRBO COWORKING MTL") == ExpenseCategory.COWORKING

    def test_meals(self):
        assert categorize("SQ *CAFE MYRIADE") == ExpenseCategory.MEALS
        assert categorize("LE PETIT DEP REST") == ExpenseCategory.MEALS

    def test_hosting(self):
        assert categorize("NAMECHEAP.COM") == ExpenseCategory.HOSTING

    def test_unknown(self):
        assert categorize("RANDOM VENDOR XYZ") == ExpenseCategory.OTHER


#  API integration tests 


@pytest.fixture
def client():
    transport = ASGITransport(app=app)
    return AsyncClient(transport=transport, base_url="http://test")


def _upload_file(name, content, content_type="application/octet-stream"):
    return ("files", (name, io.BytesIO(content), content_type))


@pytest.mark.asyncio
async def test_normalize_before_extract(client):
    """Normalize without extracting first should fail."""
    async with client as c:
        r = await c.post("/api/upload", files=[_upload_file("x.txt", b"data")])
        job_id = r.json()["job_id"]

        r = await c.post(f"/api/jobs/{job_id}/normalize")
    assert r.status_code == 400


@pytest.mark.asyncio
async def test_process_one_shot(client):
    """Process endpoint runs extract + normalize + reconcile in one call."""
    async with client as c:
        r = await c.post("/api/upload", files=[_upload_file("notes.txt", b"[todo] pay rent")])
        job_id = r.json()["job_id"]

        r = await c.post(f"/api/jobs/{job_id}/process")

    assert r.status_code == 200
    data = r.json()
    assert "normalized" in data
    assert "reconciliation" in data
    assert data["normalized"]["job_id"] == job_id


@pytest.mark.asyncio
async def test_full_shoebox_normalize(client):
    """End-to-end: upload shoebox → extract → normalize → verify everything."""
    if not SHOEBOX_PATH.exists():
        pytest.skip("shoebox.zip not found")

    zip_bytes = SHOEBOX_PATH.read_bytes()

    async with client as c:
        # Upload
        r = await c.post(
            "/api/upload",
            files=[_upload_file("shoebox.zip", zip_bytes, "application/zip")],
        )
        job_id = r.json()["job_id"]

        # Extract
        await c.post(f"/api/jobs/{job_id}/extract")

        # Normalize
        r = await c.post(f"/api/jobs/{job_id}/normalize")

    assert r.status_code == 200
    data = r.json()

    #  Expenses 
    expenses = data["expenses"]
    assert len(expenses) > 30  # 36 CC + receipts

    # Personal charges flagged
    personal = [e for e in expenses if e["is_personal"]]
    assert len(personal) == 4  # Netflix x3 + Petco x1

    # All personal charges are non-deductible
    assert all(not e["tax_deductible"] for e in personal)

    # Duplicates flagged
    dups = [e for e in expenses if e["is_duplicate"]]
    assert len(dups) == 3  # Adobe, Shopify, VRBO

    # Refunds detected
    refunds = [e for e in expenses if e["is_refund"]]
    assert len(refunds) == 2  # Adobe -$40, Staples -$32.49

    # Categories assigned
    categories = {e["category"] for e in expenses}
    assert "Software & Subscriptions" in categories
    assert "Office Supplies" in categories
    assert "Personal (Non-Deductible)" in categories

    #  Invoices 
    invoices = data["invoices"]
    assert len(invoices) == 9

    outstanding = [i for i in invoices if i["status"] == "Outstanding"]
    assert len(outstanding) == 2

    paid = [i for i in invoices if i["status"] == "Paid"]
    assert all(i["days_to_payment"] is not None for i in paid)

    #  Action items 
    actions = data["action_items"]
    assert len(actions) > 5

    todos = [a for a in actions if not a["done"]]
    assert len(todos) >= 2  # greenloop + atelier nomade

    #  Totals 
    totals = data["totals"]
    assert totals["gross_revenue"] == 14250.0
    assert totals["outstanding_revenue"] == 3250.0
    assert totals["personal_charges_flagged"] == 4
    assert totals["duplicates_flagged"] == 3
    assert totals["invoices_outstanding"] == 2
    assert totals["net_income"] > 0
    assert totals["avg_payment_days"] > 0

    # Category breakdown should exist
    assert len(totals["expenses_by_category"]) > 3
    assert len(totals["expenses_by_month"]) == 3  # Jan, Feb, Mar
    assert len(totals["revenue_by_client"]) == 5


@pytest.mark.asyncio
async def test_get_normalized_after_normalize(client):
    async with client as c:
        r = await c.post("/api/upload", files=[_upload_file("n.txt", b"hello")])
        job_id = r.json()["job_id"]

        await c.post(f"/api/jobs/{job_id}/extract")
        await c.post(f"/api/jobs/{job_id}/normalize")

        r = await c.get(f"/api/jobs/{job_id}/normalize")

    assert r.status_code == 200
    assert r.json()["job_id"] == job_id


@pytest.mark.asyncio
async def test_normalize_feature_flag(client):
    async with client as c:
        r = await c.get("/api/status")
    assert r.json()["features"]["normalize"] is True
