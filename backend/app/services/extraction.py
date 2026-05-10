"""
Extraction orchestrator — takes a classified job and runs the right
extractor on each file.
"""

from __future__ import annotations

from app.models.schemas import (
    ExtractionResult,
    FileInfo,
    FileType,
    Job,
    JobStatus,
)
from app.extractors.pdf_extractor import extract_pdf
from app.extractors.xlsx_extractor import extract_xlsx
from app.extractors.image_extractor import extract_image
from app.extractors.text_extractor import extract_text

# Store extraction results keyed by job_id
_results: dict[str, ExtractionResult] = {}


def get_extraction(job_id: str) -> ExtractionResult | None:
    """Retrieve extraction results for a job."""
    return _results.get(job_id)


def run_extraction(job: Job) -> ExtractionResult:
    """
    Run extractors on all files in a job.

    Dispatches each file to the right extractor based on its classified type.
    Collects all results and warnings into a single ExtractionResult.
    """
    result = ExtractionResult(job_id=job.job_id)

    for file_info in job.files:
        try:
            _extract_file(file_info, result)
        except Exception as e:
            result.warnings.append(
                f"Extraction failed for '{file_info.filename}': {e}"
            )

    # Update job status
    job.status = JobStatus.PROCESSING

    # Store results
    _results[job.job_id] = result

    return result


def _extract_file(file_info: FileInfo, result: ExtractionResult) -> None:
    """Dispatch a single file to the right extractor."""

    if file_info.file_type == FileType.PDF_STATEMENT:
        transactions, warnings = extract_pdf(file_info.stored_path)
        result.transactions.extend(transactions)
        result.warnings.extend(warnings)

    elif file_info.file_type == FileType.SPREADSHEET:
        invoices, warnings = extract_xlsx(file_info.stored_path)
        result.invoices.extend(invoices)
        result.warnings.extend(warnings)

    elif file_info.file_type == FileType.IMAGE_RECEIPT:
        receipt, warnings = extract_image(file_info.stored_path)
        result.receipts.append(receipt)
        result.warnings.extend(warnings)

    elif file_info.file_type == FileType.TEXT_NOTES:
        notes, warnings = extract_text(file_info.stored_path)
        result.notes.append(notes)
        result.warnings.extend(warnings)

    else:
        result.warnings.append(
            f"No extractor for file type '{file_info.file_type}': {file_info.filename}"
        )
