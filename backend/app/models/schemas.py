from __future__ import annotations

import enum
from datetime import datetime, timezone
from pydantic import BaseModel, Field


class FileType(str, enum.Enum):
    """What we think a file is, based on extension + content sniffing."""

    PDF_STATEMENT = "pdf_statement"
    SPREADSHEET = "spreadsheet"
    IMAGE_RECEIPT = "image_receipt"
    TEXT_NOTES = "text_notes"
    ARCHIVE = "archive"
    UNKNOWN = "unknown"
    JUNK = "junk"


class JobStatus(str, enum.Enum):
    """Job lifecycle: uploaded > classified > processing > done > error."""

    UPLOADED = "uploaded"
    CLASSIFIED = "classified"
    PROCESSING = "processing"
    DONE = "done"
    ERROR = "error"


class FileInfo(BaseModel):
    """Metadata about a single file within a job."""

    filename: str
    original_path: str  # path while uploaded or within the zip uploaded  (e.g. "shoebox/receipts/beg.png")
    stored_path: str  # absolute path on disk
    size_bytes: int
    file_type: FileType = FileType.UNKNOWN
    mime_hint: str = ""

    model_config = {"from_attributes": True}


class Job(BaseModel):
    """A single upload job — tracks files from intake through to results."""

    job_id: str
    status: JobStatus = JobStatus.UPLOADED
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    files: list[FileInfo] = Field(default_factory=list)
    file_count: int = 0
    total_size_bytes: int = 0
    errors: list[str] = Field(default_factory=list)

    model_config = {"from_attributes": True}


# Response schemas


class UploadResponse(BaseModel):
    job_id: str
    status: JobStatus
    file_count: int
    files: list[FileInfo]


class JobStatusResponse(BaseModel):
    job_id: str
    status: JobStatus
    created_at: datetime
    file_count: int
    total_size_bytes: int
    files: list[FileInfo]
    errors: list[str]
