"""
Tests for the reconciliation feature.

Covers: refund matching, missing receipts, overdue invoices,
anomaly detection, tax summary, data quality, insights, and full pipeline.
"""

import io
from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app


SHOEBOX_PATH = Path(__file__).parent.parent.parent / "data" / "shoebox.zip"
if not SHOEBOX_PATH.exists():
    SHOEBOX_PATH = Path("/home/claude/tablo/data/shoebox.zip")


@pytest.fixture
def client():
    transport = ASGITransport(app=app)
    return AsyncClient(transport=transport, base_url="http://test")


def _upload_file(name, content, content_type="application/octet-stream"):
    return ("files", (name, io.BytesIO(content), content_type))


async def _upload_and_process(c, zip_bytes):
    """Helper: upload shoebox → extract → normalize → reconcile."""
    r = await c.post(
        "/api/upload",
        files=[_upload_file("shoebox.zip", zip_bytes, "application/zip")],
    )
    job_id = r.json()["job_id"]

    await c.post(f"/api/jobs/{job_id}/extract")
    await c.post(f"/api/jobs/{job_id}/normalize")
    r = await c.post(f"/api/jobs/{job_id}/reconcile")
    return job_id, r


@pytest.mark.asyncio
async def test_reconcile_before_normalize(client):
    """Reconcile without normalizing first should fail."""
    async with client as c:
        r = await c.post("/api/upload", files=[_upload_file("x.txt", b"data")])
        job_id = r.json()["job_id"]

        r = await c.post(f"/api/jobs/{job_id}/reconcile")
    assert r.status_code == 400


@pytest.mark.asyncio
async def test_full_reconciliation(client):
    """End-to-end reconciliation on the real shoebox data."""
    if not SHOEBOX_PATH.exists():
        pytest.skip("shoebox.zip not found")

    zip_bytes = SHOEBOX_PATH.read_bytes()

    async with client as c:
        job_id, r = await _upload_and_process(c, zip_bytes)

    assert r.status_code == 200
    data = r.json()

    #  Refund matches 
    matches = data["refund_matches"]
    assert len(matches) == 2  # Adobe + Staples refunds

    # Adobe refund should match an Adobe charge
    adobe_match = [m for m in matches if "ADOBE" in m["refund_description"]]
    assert len(adobe_match) == 1
    assert adobe_match[0]["refund_amount"] == -40.0
    assert "ADOBE" in adobe_match[0]["original_description"]

    # Staples refund should match Staples charge
    staples_match = [m for m in matches if "STAPLES" in m["refund_description"]]
    assert len(staples_match) == 1
    assert staples_match[0]["refund_amount"] == -32.49
    assert abs(staples_match[0]["original_amount"]) == 32.49
    assert staples_match[0]["match_confidence"] == "high"  # exact amount match

    #  Missing receipts 
    missing = data["missing_receipts"]
    assert len(missing) > 0  # CC charges above $25 without receipts

    # Adobe charges should be in missing receipts (no receipt for CC charges)
    adobe_missing = [m for m in missing if "ADOBE" in m["description"]]
    assert len(adobe_missing) > 0

    #  Overdue invoices 
    overdue = data["overdue_invoices"]
    assert len(overdue) == 2  # GreenLoop + Atelier Nomade
    clients = {o["client"] for o in overdue}
    assert "GreenLoop Technologies" in clients
    assert "Atelier Nomade" in clients
    assert all(o["days_outstanding"] > 0 for o in overdue)

    #  Anomalies 
    anomalies = data["anomalies"]
    # Anomalies are charges >30% different from the merchant average
    # The exact list depends on data — just verify structure
    for a in anomalies:
        assert "date" in a
        assert "amount" in a
        assert "usual_amount" in a
        assert a["deviation_pct"] > 30

    #  Tax summary 
    tax = data["tax_summary"]
    assert tax["total_deductible"] > 0
    assert tax["total_non_deductible"] > 0  # Netflix + Petco
    assert tax["refunds_total"] > 0
    assert tax["net_deductible"] > 0
    assert len(tax["deductible_by_category"]) > 3

    #  Data quality 
    quality = data["data_quality"]
    assert 0 <= quality["score"] <= 100
    assert len(quality["issues"]) > 0
    assert len(quality["recommendations"]) > 0

    #  Insights 
    insights = data["insights"]
    assert len(insights) > 3
    # Should mention revenue, margin, payment speed, top client
    all_text = " ".join(insights).lower()
    assert "revenue" in all_text or "q1" in all_text
    assert "margin" in all_text or "net" in all_text


@pytest.mark.asyncio
async def test_process_one_shot_includes_reconciliation(client):
    """The /process endpoint should now include reconciliation."""
    if not SHOEBOX_PATH.exists():
        pytest.skip("shoebox.zip not found")

    zip_bytes = SHOEBOX_PATH.read_bytes()

    async with client as c:
        r = await c.post(
            "/api/upload",
            files=[_upload_file("shoebox.zip", zip_bytes, "application/zip")],
        )
        job_id = r.json()["job_id"]

        r = await c.post(f"/api/jobs/{job_id}/process")

    assert r.status_code == 200
    data = r.json()

    # Should have both normalized and reconciliation sections
    assert "normalized" in data
    assert "reconciliation" in data
    assert data["reconciliation"]["job_id"] == job_id
    assert len(data["reconciliation"]["refund_matches"]) == 2
    assert len(data["normalized"]["expenses"]) > 30


@pytest.mark.asyncio
async def test_get_reconciliation_after_reconcile(client):
    if not SHOEBOX_PATH.exists():
        pytest.skip("shoebox.zip not found")

    zip_bytes = SHOEBOX_PATH.read_bytes()

    async with client as c:
        job_id, _ = await _upload_and_process(c, zip_bytes)
        r = await c.get(f"/api/jobs/{job_id}/reconcile")

    assert r.status_code == 200
    assert r.json()["job_id"] == job_id


@pytest.mark.asyncio
async def test_reconcile_feature_flag(client):
    async with client as c:
        r = await c.get("/api/status")
    assert r.json()["features"]["reconcile"] is True
