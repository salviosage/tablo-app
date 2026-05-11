"""
Tests for the extractors feature.

Covers: PDF parsing, XLSX parsing, image OCR, text extraction,
orchestrator dispatch, and end-to-end extraction on real shoebox data.
"""

import io
import zipfile
from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app
from app.extractors.pdf_extractor import extract_pdf
from app.extractors.xlsx_extractor import extract_xlsx, _parse_date
from app.extractors.text_extractor import extract_text


SHOEBOX_PATH = Path(__file__).parent.parent.parent / "data" / "shoebox.zip"
if not SHOEBOX_PATH.exists():
    SHOEBOX_PATH = Path("/home/claude/tablo/data/shoebox.zip")


def _get_shoebox_file(name: str) -> Path | None:
    """Extract a specific file from shoebox.zip to a temp location."""
    if not SHOEBOX_PATH.exists():
        return None
    import tempfile
    import zipfile as zf

    with zf.ZipFile(SHOEBOX_PATH, "r") as z:
        for member in z.namelist():
            if member.endswith(name):
                tmp = Path(tempfile.mkdtemp()) / name
                with z.open(member) as src:
                    tmp.write_bytes(src.read())
                return tmp
    return None


#  Date parsing unit tests 


class TestDateParsing:
    def test_us_slash(self):
        assert _parse_date("1/5/2025") == "2025-01-05"

    def test_short_year_slash(self):
        assert _parse_date("3/18/25") == "2025-03-18"

    def test_long_month(self):
        assert _parse_date("February 15, 2025") == "2025-02-15"

    def test_short_month_comma(self):
        assert _parse_date("Jan 18, 25") == "2025-01-18"

    def test_dash_separator(self):
        assert _parse_date("Mar 28 - 2025") == "2025-03-28"

    def test_month_day_space_year(self):
        assert _parse_date("Jan 30 2025") == "2025-01-30"

    def test_none(self):
        assert _parse_date(None) is None

    def test_empty(self):
        assert _parse_date("") is None


#  PDF extractor 


class TestPdfExtractor:
    def test_real_pdf(self):
        pdf_path = _get_shoebox_file("Visa_Statement_Q12025.pdf")
        if pdf_path is None:
            pytest.skip("shoebox.zip not found")

        transactions, warnings = extract_pdf(str(pdf_path))

        assert len(transactions) == 36
        assert all(t.transaction_id.startswith("TXN-") for t in transactions)
        assert all(t.source_file == "Visa_Statement_Q12025.pdf" for t in transactions)

        # Check a known transaction
        adobe = [t for t in transactions if "ADOBE" in t.description and t.date == "2025-01-06"]
        assert len(adobe) == 2  # duplicate
        assert adobe[0].amount == 74.99

        # Check refund (negative amount)
        refunds = [t for t in transactions if t.amount < 0]
        assert len(refunds) == 2

    def test_empty_pdf(self, tmp_path):
        p = tmp_path / "empty.pdf"
        p.write_bytes(b"%PDF-1.4 no real content")
        transactions, warnings = extract_pdf(str(p))
        assert len(transactions) == 0
        assert len(warnings) > 0


#  XLSX extractor 


class TestXlsxExtractor:
    def test_real_xlsx(self):
        xlsx_path = _get_shoebox_file("invoices.xlsx")
        if xlsx_path is None:
            pytest.skip("shoebox.zip not found")

        invoices, warnings = extract_xlsx(str(xlsx_path))

        assert len(invoices) == 9
        assert all(i.source_file == "invoices.xlsx" for i in invoices)

        # Check known client
        brightpath = [i for i in invoices if "BrightPath" in i.client]
        assert len(brightpath) == 3
        assert all(i.amount == 3500.0 for i in brightpath)

        # Check outstanding (no date_paid)
        outstanding = [i for i in invoices if i.date_paid is None or i.date_paid == ""]
        assert len(outstanding) == 2

        # Should warn about empty rows
        assert any("empty rows" in w for w in warnings)


#  Text extractor 


class TestTextExtractor:
    def test_real_notes(self):
        notes_path = _get_shoebox_file("notes.txt")
        if notes_path is None:
            pytest.skip("shoebox.zip not found")

        notes, warnings = extract_text(str(notes_path))

        assert notes.raw_text != ""
        assert len(notes.lines) > 5
        assert notes.source_file == "notes.txt"

        # Should contain key content
        assert any("petco" in line.lower() for line in notes.lines)
        assert any("netflix" in line.lower() for line in notes.lines)
        assert any("[todo]" in line.lower() for line in notes.lines)

    def test_empty_file(self, tmp_path):
        p = tmp_path / "empty.txt"
        p.write_text("")
        notes, warnings = extract_text(str(p))
        assert notes.raw_text == ""
        assert len(notes.lines) == 0


#  API integration tests 


@pytest.fixture
def client():
    transport = ASGITransport(app=app)
    return AsyncClient(transport=transport, base_url="http://test")


def _upload_file(name, content, content_type="application/octet-stream"):
    return ("files", (name, io.BytesIO(content), content_type))


def _make_zip(file_map):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        for name, content in file_map.items():
            zf.writestr(name, content)
    return buf.getvalue()


@pytest.mark.asyncio
async def test_extract_endpoint(client):
    """Upload a text file, then extract it."""
    async with client as c:
        r = await c.post("/api/upload", files=[_upload_file("test.txt", b"hello world")])
        job_id = r.json()["job_id"]

        r = await c.post(f"/api/jobs/{job_id}/extract")

    assert r.status_code == 200
    data = r.json()
    assert data["job_id"] == job_id
    assert len(data["notes"]) == 1
    assert "hello world" in data["notes"][0]["raw_text"]


@pytest.mark.asyncio
async def test_extract_not_found(client):
    async with client as c:
        r = await c.post("/api/jobs/nonexistent/extract")
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_get_extraction_before_extract(client):
    """GET extraction results before running extract should 404."""
    async with client as c:
        r = await c.post("/api/upload", files=[_upload_file("x.txt", b"data")])
        job_id = r.json()["job_id"]

        r = await c.get(f"/api/jobs/{job_id}/extract")
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_get_extraction_after_extract(client):
    """GET extraction results after running extract should work."""
    async with client as c:
        r = await c.post("/api/upload", files=[_upload_file("x.txt", b"data")])
        job_id = r.json()["job_id"]

        await c.post(f"/api/jobs/{job_id}/extract")
        r = await c.get(f"/api/jobs/{job_id}/extract")

    assert r.status_code == 200
    assert r.json()["job_id"] == job_id


@pytest.mark.asyncio
async def test_full_shoebox_extraction(client):
    """End-to-end: upload the real shoebox.zip, then extract everything."""
    if not SHOEBOX_PATH.exists():
        pytest.skip("shoebox.zip not found")

    zip_bytes = SHOEBOX_PATH.read_bytes()

    async with client as c:
        r = await c.post(
            "/api/upload",
            files=[_upload_file("shoebox.zip", zip_bytes, "application/zip")],
        )
        job_id = r.json()["job_id"]

        r = await c.post(f"/api/jobs/{job_id}/extract")

    assert r.status_code == 200
    data = r.json()

    # PDF: 36 transactions
    assert len(data["transactions"]) == 36

    # XLSX: 9 invoices
    assert len(data["invoices"]) == 9

    # Images: 5 receipt files processed
    assert len(data["receipts"]) == 5

    # Text: 1 notes file
    assert len(data["notes"]) == 1
    assert "petco" in data["notes"][0]["raw_text"].lower()

    # Should have some warnings (empty rows, etc.)
    assert len(data["warnings"]) > 0


@pytest.mark.asyncio
async def test_extractors_feature_flag(client):
    async with client as c:
        r = await c.get("/api/status")
    assert r.json()["features"]["extractors"] is True
