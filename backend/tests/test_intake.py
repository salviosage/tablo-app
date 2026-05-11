"""
Tests for the intake feature.

Covers: file upload, zip extraction, file classification,
job creation, job retrieval, job deletion, edge cases.
"""

import io
import zipfile
from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app
from app.models.schemas import FileType
from app.services.classifier import classify_file


#  Classifier unit tests 


class TestClassifier:
    def test_pdf(self, tmp_path):
        p = tmp_path / "statement.pdf"
        p.write_bytes(b"%PDF-1.4 fake pdf content")
        ft, mime = classify_file(p)
        assert ft == FileType.PDF_STATEMENT

    def test_xlsx(self, tmp_path):
        p = tmp_path / "invoices.xlsx"
        p.write_bytes(b"fake xlsx")
        ft, mime = classify_file(p)
        assert ft == FileType.SPREADSHEET

    def test_csv(self, tmp_path):
        p = tmp_path / "data.csv"
        p.write_text("a,b,c\n1,2,3")
        ft, mime = classify_file(p)
        assert ft == FileType.SPREADSHEET

    def test_txt(self, tmp_path):
        p = tmp_path / "notes.txt"
        p.write_text("some notes here")
        ft, mime = classify_file(p)
        assert ft == FileType.TEXT_NOTES

    def test_png(self, tmp_path):
        p = tmp_path / "receipt.png"
        # minimal valid PNG header
        p.write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 100)
        ft, mime = classify_file(p)
        assert ft == FileType.IMAGE_RECEIPT

    def test_jpeg(self, tmp_path):
        p = tmp_path / "photo.jpeg"
        p.write_bytes(b"\xff\xd8\xff\xe0" + b"\x00" * 100)
        ft, mime = classify_file(p)
        assert ft == FileType.IMAGE_RECEIPT

    def test_jpg(self, tmp_path):
        p = tmp_path / "photo.jpg"
        p.write_bytes(b"\xff\xd8\xff\xe0" + b"\x00" * 100)
        ft, mime = classify_file(p)
        assert ft == FileType.IMAGE_RECEIPT

    def test_ds_store_is_junk(self, tmp_path):
        p = tmp_path / ".DS_Store"
        p.write_bytes(b"\x00\x00\x00\x01Bud1")
        ft, mime = classify_file(p)
        assert ft == FileType.JUNK

    def test_hidden_file_is_junk(self, tmp_path):
        p = tmp_path / ".hidden"
        p.write_text("hidden")
        ft, mime = classify_file(p)
        assert ft == FileType.JUNK

    def test_unknown_extension(self, tmp_path):
        p = tmp_path / "mystery.xyz"
        p.write_bytes(b"\x80\x81\x82\x83\xff\xfe\xfd")  # invalid UTF-8
        ft, mime = classify_file(p)
        assert ft == FileType.UNKNOWN

    def test_no_extension_text(self, tmp_path):
        p = tmp_path / "README"
        p.write_text("this is a readme")
        ft, mime = classify_file(p)
        assert ft == FileType.TEXT_NOTES

    def test_no_extension_pdf(self, tmp_path):
        p = tmp_path / "document"
        p.write_bytes(b"%PDF-1.4 this is a pdf")
        ft, mime = classify_file(p)
        assert ft == FileType.PDF_STATEMENT


#  Helper to build test files 


def _make_zip(file_map: dict[str, bytes]) -> bytes:
    """Create an in-memory zip from {filename: content}."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        for name, content in file_map.items():
            zf.writestr(name, content)
    return buf.getvalue()


def _upload_file(name: str, content: bytes, content_type: str = "application/octet-stream"):
    """Create a tuple for httpx file upload."""
    return ("files", (name, io.BytesIO(content), content_type))


#  API integration tests 


@pytest.fixture
def client():
    transport = ASGITransport(app=app)
    return AsyncClient(transport=transport, base_url="http://test")


@pytest.mark.asyncio
async def test_upload_single_txt(client):
    async with client as c:
        r = await c.post(
            "/api/upload",
            files=[_upload_file("notes.txt", b"my notes")],
        )
    assert r.status_code == 200
    data = r.json()
    assert data["file_count"] == 1
    assert data["files"][0]["filename"] == "notes.txt"
    assert data["files"][0]["file_type"] == "text_notes"
    assert data["status"] == "classified"


@pytest.mark.asyncio
async def test_upload_multiple_files(client):
    async with client as c:
        r = await c.post(
            "/api/upload",
            files=[
                _upload_file("notes.txt", b"my notes"),
                _upload_file("invoice.xlsx", b"fake xlsx"),
                _upload_file("statement.pdf", b"%PDF-1.4 content"),
            ],
        )
    assert r.status_code == 200
    data = r.json()
    assert data["file_count"] == 3

    types = {f["filename"]: f["file_type"] for f in data["files"]}
    assert types["notes.txt"] == "text_notes"
    assert types["invoice.xlsx"] == "spreadsheet"
    assert types["statement.pdf"] == "pdf_statement"


@pytest.mark.asyncio
async def test_upload_zip(client):
    zip_bytes = _make_zip({
        "shoebox/notes.txt": b"my notes",
        "shoebox/invoices.xlsx": b"fake xlsx",
        "shoebox/Visa_Statement.pdf": b"%PDF-1.4 content",
        "shoebox/receipts/beg.png": b"\x89PNG\r\n\x1a\n" + b"\x00" * 100,
        "shoebox/receipts/parking.jpeg": b"\xff\xd8\xff\xe0" + b"\x00" * 100,
    })

    async with client as c:
        r = await c.post(
            "/api/upload",
            files=[_upload_file("shoebox.zip", zip_bytes, "application/zip")],
        )
    assert r.status_code == 200
    data = r.json()
    assert data["file_count"] == 5
    assert data["status"] == "classified"

    types = {f["filename"]: f["file_type"] for f in data["files"]}
    assert types["notes.txt"] == "text_notes"
    assert types["invoices.xlsx"] == "spreadsheet"
    assert types["Visa_Statement.pdf"] == "pdf_statement"
    assert types["beg.png"] == "image_receipt"
    assert types["parking.jpeg"] == "image_receipt"


@pytest.mark.asyncio
async def test_zip_skips_macosx_junk(client):
    zip_bytes = _make_zip({
        "shoebox/notes.txt": b"real file",
        "__MACOSX/._notes.txt": b"apple junk",
        "shoebox/.DS_Store": b"\x00\x00\x00\x01Bud1",
    })

    async with client as c:
        r = await c.post(
            "/api/upload",
            files=[_upload_file("data.zip", zip_bytes)],
        )
    data = r.json()
    assert data["file_count"] == 1
    assert data["files"][0]["filename"] == "notes.txt"


@pytest.mark.asyncio
async def test_get_job(client):
    async with client as c:
        # Upload first
        r = await c.post(
            "/api/upload",
            files=[_upload_file("test.txt", b"hello")],
        )
        job_id = r.json()["job_id"]

        # Retrieve
        r = await c.get(f"/api/jobs/{job_id}")
    assert r.status_code == 200
    data = r.json()
    assert data["job_id"] == job_id
    assert data["status"] == "classified"
    assert data["file_count"] == 1
    assert data["total_size_bytes"] > 0


@pytest.mark.asyncio
async def test_get_job_not_found(client):
    async with client as c:
        r = await c.get("/api/jobs/nonexistent")
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_list_jobs(client):
    async with client as c:
        # Upload two jobs
        await c.post("/api/upload", files=[_upload_file("a.txt", b"aaa")])
        await c.post("/api/upload", files=[_upload_file("b.txt", b"bbb")])

        r = await c.get("/api/jobs")
    assert r.status_code == 200
    data = r.json()
    assert data["count"] >= 2


@pytest.mark.asyncio
async def test_delete_job(client):
    async with client as c:
        r = await c.post("/api/upload", files=[_upload_file("x.txt", b"delete me")])
        job_id = r.json()["job_id"]

        # Delete
        r = await c.delete(f"/api/jobs/{job_id}")
        assert r.status_code == 200
        assert r.json()["deleted"] is True

        # Should be gone
        r = await c.get(f"/api/jobs/{job_id}")
        assert r.status_code == 404


@pytest.mark.asyncio
async def test_delete_job_not_found(client):
    async with client as c:
        r = await c.delete("/api/jobs/nonexistent")
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_upload_real_shoebox(client):
    """Integration test with the actual shoebox.zip test data."""
    shoebox_path = Path(__file__).parent.parent.parent / "data" / "shoebox.zip"
    if not shoebox_path.exists():
        # Try alternative path
        shoebox_path = Path("/home/claude/tablo/data/shoebox.zip")
    if not shoebox_path.exists():
        pytest.skip("shoebox.zip not found")

    zip_bytes = shoebox_path.read_bytes()

    async with client as c:
        r = await c.post(
            "/api/upload",
            files=[_upload_file("shoebox.zip", zip_bytes, "application/zip")],
        )

    assert r.status_code == 200
    data = r.json()

    # Should find: 1 PDF, 1 XLSX, 1 TXT, 5 images
    types = [f["file_type"] for f in data["files"]]
    assert types.count("pdf_statement") == 1
    assert types.count("spreadsheet") == 1
    assert types.count("text_notes") == 1
    assert types.count("image_receipt") == 5  # beg, parking, artsupplies, pharmacy, chat_gpt

    assert data["file_count"] == 8
    assert data["status"] == "classified"


@pytest.mark.asyncio
async def test_status_shows_intake_enabled(client):
    async with client as c:
        r = await c.get("/api/status")
    data = r.json()
    assert data["features"]["intake"] is True


#  Nested zip tests 


@pytest.mark.asyncio
async def test_nested_zip_is_extracted(client):
    """A zip inside a zip should be recursively extracted — not classified as a spreadsheet."""
    # Inner zip containing a note and a fake PDF
    inner_zip = _make_zip({
        "inner/doc.txt": b"inner document",
        "inner/report.pdf": b"%PDF-1.4 inner pdf",
    })

    # Outer zip containing the inner zip + another file
    outer_zip = _make_zip({
        "folder/notes.txt": b"outer notes",
        "folder/archive.zip": inner_zip,
    })

    async with client as c:
        r = await c.post(
            "/api/upload",
            files=[_upload_file("bundle.zip", outer_zip)],
        )

    assert r.status_code == 200
    data = r.json()

    # Inner zip should be extracted — we should see 3 files, not 2
    filenames = {f["filename"] for f in data["files"]}
    assert "notes.txt" in filenames
    assert "doc.txt" in filenames
    assert "report.pdf" in filenames
    assert data["file_count"] == 3

    # archive.zip should NOT appear as a file
    assert "archive.zip" not in filenames

    # Nothing should be classified as "archive"
    types = [f["file_type"] for f in data["files"]]
    assert "archive" not in types


@pytest.mark.asyncio
async def test_xlsx_not_classified_as_archive(client):
    """An .xlsx file is a zip internally but should stay classified as spreadsheet."""
    async with client as c:
        r = await c.post(
            "/api/upload",
            files=[_upload_file("data.xlsx", b"PK\x03\x04 fake xlsx")],
        )
    data = r.json()
    assert data["file_count"] == 1
    assert data["files"][0]["file_type"] == "spreadsheet"


@pytest.mark.asyncio
async def test_zip_with_shoebox_inside(client):
    """
    The exact user scenario: shoebox.zip placed alongside other files in a folder,
    then the whole folder is zipped. The inner shoebox.zip must be extracted.
    """
    shoebox_path = Path(__file__).parent.parent.parent / "data" / "shoebox.zip"
    if not shoebox_path.exists():
        shoebox_path = Path("/home/claude/tablo/data/shoebox.zip")
    if not shoebox_path.exists():
        pytest.skip("shoebox.zip not found")

    shoebox_bytes = shoebox_path.read_bytes()

    # Simulate: user puts shoebox.zip + a notes.txt in a folder, zips it
    outer_zip = _make_zip({
        "testfile/notes.txt": b"extra notes on top",
        "testfile/shoebox.zip": shoebox_bytes,
        "testfile/invoices.xlsx": b"PK\x03\x04 another xlsx",
    })

    async with client as c:
        r = await c.post(
            "/api/upload",
            files=[_upload_file("everything.zip", outer_zip)],
        )

    assert r.status_code == 200
    data = r.json()

    # Should NOT have any file classified as "archive"
    types = [f["file_type"] for f in data["files"]]
    assert "archive" not in types

    # The inner shoebox should be fully extracted (1 PDF + 1 XLSX + 1 TXT + 5 images = 8)
    # plus the outer notes.txt and invoices.xlsx = 10 total
    assert data["file_count"] == 10

    # Check the shoebox contents made it through
    filenames = {f["filename"] for f in data["files"]}
    assert "Visa_Statement_Q12025.pdf" in filenames
    assert "parking.jpeg" in filenames
    assert "beg.png" in filenames


class TestClassifierZipVsXlsx:
    """Verify the classifier distinguishes zip archives from xlsx files."""

    def test_plain_zip_classified_as_archive(self, tmp_path):
        p = tmp_path / "data.zip"
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as zf:
            zf.writestr("hello.txt", "world")
        p.write_bytes(buf.getvalue())

        ft, mime = classify_file(p)
        assert ft == FileType.ARCHIVE

    def test_xlsx_by_extension(self, tmp_path):
        p = tmp_path / "invoices.xlsx"
        p.write_bytes(b"fake xlsx content")
        ft, mime = classify_file(p)
        assert ft == FileType.SPREADSHEET

    def test_zip_extension_is_archive(self, tmp_path):
        p = tmp_path / "stuff.zip"
        p.write_bytes(b"PK\x03\x04 not important")
        ft, mime = classify_file(p)
        assert ft == FileType.ARCHIVE
