"""
File classifier — looks at a file and decides what type it is.

Uses extension first (fast), then content sniffing for ambiguous cases.
"""

from __future__ import annotations

import mimetypes
from pathlib import Path

from app.models.schemas import FileType


# Magic bytes for common image formats
IMAGE_SIGNATURES: list[tuple[bytes, str]] = [
    (b"\x89PNG\r\n\x1a\n", "image/png"),
    (b"\xff\xd8\xff", "image/jpeg"),
    (b"GIF87a", "image/gif"),
    (b"GIF89a", "image/gif"),
    (b"BM", "image/bmp"),
    (b"RIFF", "image/webp"),  
    (b"II\x2a\x00", "image/tiff"),
    (b"MM\x00\x2a", "image/tiff"),
]


# Extension > FileType mapping
EXTENSION_MAP: dict[str, FileType] = {
    ".pdf": FileType.PDF_STATEMENT,
    ".xlsx": FileType.SPREADSHEET,
    ".xls": FileType.SPREADSHEET,
    ".csv": FileType.SPREADSHEET,
    ".tsv": FileType.SPREADSHEET,
    ".txt": FileType.TEXT_NOTES,
    ".md": FileType.TEXT_NOTES,
    ".zip": FileType.ARCHIVE,
    ".tar": FileType.ARCHIVE,
    ".gz": FileType.ARCHIVE,
    ".rar": FileType.ARCHIVE,
    ".7z": FileType.ARCHIVE,
    ".png": FileType.IMAGE_RECEIPT,
    ".jpg": FileType.IMAGE_RECEIPT,
    ".jpeg": FileType.IMAGE_RECEIPT,
    ".gif": FileType.IMAGE_RECEIPT,
    ".webp": FileType.IMAGE_RECEIPT,
    ".heic": FileType.IMAGE_RECEIPT,
    ".tiff": FileType.IMAGE_RECEIPT,
    ".tif": FileType.IMAGE_RECEIPT,
    ".bmp": FileType.IMAGE_RECEIPT,
}

# Files we should skip entirely
JUNK_PATTERNS: set[str] = {
    ".ds_store",
    "thumbs.db",
    "desktop.ini",
    "__macosx",
}


def classify_file(path: Path) -> tuple[FileType, str]:
    """
    Classify a file by its type.

    Returns:
        (file_type, mime_hint)
    """
    name_lower = path.name.lower()

    # Skip OS junk files
    if name_lower in JUNK_PATTERNS or name_lower.startswith("."):
        return FileType.JUNK, ""

    # Skip __MACOSX directories 
    if "__macosx" in str(path).lower():
        return FileType.JUNK, ""

    # Extension-based classification
    suffix = path.suffix.lower()
    mime_hint = mimetypes.guess_type(str(path))[0] or ""

    if suffix in EXTENSION_MAP:
        return EXTENSION_MAP[suffix], mime_hint

    # Content sniffing for files with no/unknown extension
    if path.is_file() and path.stat().st_size > 0:
        return _sniff_content(path, mime_hint)

    return FileType.UNKNOWN, mime_hint


def _classify_zip_content(path: Path) -> tuple[FileType, str]:
    """
    Distinguish between xlsx (which is a zip internally) and a plain zip archive.

    xlsx files contain specific internal files like [Content_Types].xml and xl/ directory.
    A plain zip is just a container of arbitrary files.
    """
    import zipfile

    try:
        with zipfile.ZipFile(path, "r") as zf:
            names = set(zf.namelist())

            # xlsx signature: contains [Content_Types].xml and xl/ directory
            if "[Content_Types].xml" in names and any(
                n.startswith("xl/") for n in names
            ):
                return FileType.SPREADSHEET, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"

            # docx signature (in case someone uploads one)
            if "[Content_Types].xml" in names and any(
                n.startswith("word/") for n in names
            ):
                return FileType.UNKNOWN, "application/vnd.openxmlformats-officedocument.wordprocessingml.document"

    except zipfile.BadZipFile:
        pass

    # It's a plain zip archive
    return FileType.ARCHIVE, "application/zip"
def _sniff_content(path: Path, mime_hint: str) -> tuple[FileType, str]:
    """Peek at file content to determine type when extension doesn't help."""

    try:
        with open(path, "rb") as f:
            header = f.read(12)

        # Check for image magic bytes
        for sig, img_mime in IMAGE_SIGNATURES:
            if header.startswith(sig):
                return FileType.IMAGE_RECEIPT, img_mime

        # Check for PDF magic bytes
        if header.startswith(b"%PDF"):
            return FileType.PDF_STATEMENT, "application/pdf"

        # Check for ZIP-based formats — could be xlsx, docx, or a plain zip
        if header.startswith(b"PK\x03\x04"):
            return _classify_zip_content(path)

        # Try reading as text
        try:
            with open(path, "r", encoding="utf-8") as f:
                sample = f.read(512)
            if sample.strip():
                return FileType.TEXT_NOTES, "text/plain"
        except (UnicodeDecodeError, ValueError):
            pass

    except OSError:
        pass

    return FileType.UNKNOWN, mime_hint
