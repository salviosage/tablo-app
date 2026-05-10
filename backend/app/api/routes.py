from fastapi import APIRouter, File, HTTPException, UploadFile

from app.models.schemas import ExtractionResult, JobStatusResponse, UploadResponse
from app.services import intake
from app.services.extraction import get_extraction, run_extraction

router = APIRouter()


@router.get("/status")
async def status():
    """API status check."""
    return {
        "service": "tablo-api",
        "status": "running",
        "features": {
            "intake": True,
            "extractors": True,
            "normalize": False,
            "reconcile": False,
            "dashboard": False,
        },
    }


@router.post("/upload", response_model=UploadResponse)
async def upload_files(files: list[UploadFile] = File(...)):
    """
    Upload financial documents.

    Accepts individual files or a zip archive. Files are saved,
    extracted if zipped, and classified by type.

    Returns a job ID for tracking.
    """
    if not files:
        raise HTTPException(status_code=400, detail="No files provided")

    job = await intake.create_job(files)

    if job.file_count == 0 and job.errors:
        raise HTTPException(status_code=400, detail="; ".join(job.errors))

    return UploadResponse(
        job_id=job.job_id,
        status=job.status,
        file_count=job.file_count,
        files=job.files,
    )


@router.get("/jobs/{job_id}", response_model=JobStatusResponse)
async def get_job(job_id: str):
    """Get the status and file inventory of a job."""
    job = intake.get_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")

    return JobStatusResponse(
        job_id=job.job_id,
        status=job.status,
        created_at=job.created_at,
        file_count=job.file_count,
        total_size_bytes=job.total_size_bytes,
        files=job.files,
        errors=job.errors,
    )


@router.get("/jobs")
async def list_jobs():
    """List all jobs."""
    jobs = intake.list_jobs()
    return {
        "count": len(jobs),
        "jobs": [
            {
                "job_id": j.job_id,
                "status": j.status,
                "created_at": j.created_at,
                "file_count": j.file_count,
            }
            for j in jobs
        ],
    }


@router.post("/jobs/{job_id}/extract", response_model=ExtractionResult)
async def extract_job(job_id: str):
    """
    Run extractors on all files in a job.

    Dispatches each file to the right extractor (PDF, XLSX, image OCR, text)
    based on its classified type. Returns all extracted data.
    """
    job = intake.get_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")

    if job.status not in ("classified", "processing"):
        raise HTTPException(
            status_code=400,
            detail=f"Job is in '{job.status}' state — must be 'classified' to extract",
        )

    result = run_extraction(job)
    return result


@router.get("/jobs/{job_id}/extract", response_model=ExtractionResult)
async def get_extraction_result(job_id: str):
    """Get the extraction results for a job (must have been extracted first)."""
    result = get_extraction(job_id)
    if result is None:
        raise HTTPException(
            status_code=404,
            detail="No extraction results — call POST /jobs/{job_id}/extract first",
        )
    return result


@router.delete("/jobs/{job_id}")
async def delete_job(job_id: str):
    """Delete a job and its files."""
    if not intake.delete_job(job_id):
        raise HTTPException(status_code=404, detail="Job not found")
    return {"deleted": True}
