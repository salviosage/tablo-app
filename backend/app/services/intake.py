"""Intake service — accepts uploads, extracts zips, classifies files, manages jobs."""

from __future__ import annotations

import shutil
import uuid
import zipfile
from pathlib import Path

from fastapi import UploadFile

from app.core.config import settings
from app.models.schemas import (
    FileInfo,
    FileType,
    Job,
    JobStatus,
)
from app.services.classifier import classify_file


# In-memory job store. # TODO: swap to Redis or a real DB for production
_jobs: dict[str, Job] = {}

## TODO: add security checks for files and authentication/authorization for job access

def get_job(job_id: str) -> Job | None:
    """Retrieve a job by ID."""
    return _jobs.get(job_id)


def list_jobs() -> list[Job]:
    """List all jobs, newest first."""
    return sorted(_jobs.values(), key=lambda j: j.created_at, reverse=True)


async def create_job(files: list[UploadFile]) -> Job:
    """
    Create a new job from uploaded files.

    Handles both zip archives (extracts them) and individual files.
    After saving, classifies each file by type.
    """
    job_id = uuid.uuid4().hex[:12]
    job_dir = settings.UPLOAD_DIR / job_id
    job_dir.mkdir(parents=True, exist_ok=True)

    job = Job(job_id=job_id)

    all_saved_paths: list[tuple[Path, str]] = []  # (disk_path, original_name)

    for upload in files:
        filename = upload.filename or "unnamed"
        save_path = job_dir / filename

        # Save to disk
        content = await upload.read()

        # Check size
        if len(content) > settings.MAX_UPLOAD_SIZE_MB * 1024 * 1024:
            job.errors.append(
                f"File '{filename}' exceeds {settings.MAX_UPLOAD_SIZE_MB}MB limit — skipped"
            )
            continue

        save_path.write_bytes(content)

        # If it's a zip, extract it
        if zipfile.is_zipfile(save_path):
            extracted = _extract_zip(save_path, job_dir, job)
            all_saved_paths.extend(extracted)
            save_path.unlink()  # remove the zip itself
        else:
            all_saved_paths.append((save_path, filename))

    # Classify each file — recursively extract any nested archives
    _classify_and_expand(all_saved_paths, job_dir, job)

    job.file_count = len(job.files)
    job.total_size_bytes = sum(f.size_bytes for f in job.files)
    job.status = JobStatus.CLASSIFIED

    _jobs[job_id] = job
    return job


# Max nesting depth to prevent zip bombs
_MAX_DEPTH = 5


def _classify_and_expand(
    paths: list[tuple[Path, str]],
    job_dir: Path,
    job: Job,
    depth: int = 0,
) -> None:
    """
    Classify files. If any turn out to be archives, extract and recurse.

    This handles the zip-inside-a-zip case: a user zips their shoebox folder
    alongside other files, and we need to unpack everything.
    """
    for disk_path, original_name in paths:
        if not disk_path.is_file():
            continue

        file_type, mime_hint = classify_file(disk_path)

        # Skip junk files
        if file_type == FileType.JUNK:
            disk_path.unlink(missing_ok=True)
            continue

        # If it's a nested archive, extract and recurse
        if file_type == FileType.ARCHIVE:
            if depth >= _MAX_DEPTH:
                job.errors.append(
                    f"Archive '{original_name}' exceeds max nesting depth ({_MAX_DEPTH}) — skipped"
                )
                continue

            if zipfile.is_zipfile(disk_path):
                nested = _extract_zip(disk_path, job_dir, job)
                disk_path.unlink()  # remove the archive after extraction
                _classify_and_expand(nested, job_dir, job, depth + 1)
            else:
                job.errors.append(
                    f"Archive '{original_name}' is not a supported format — skipped"
                )
            continue

        # Regular file — add to job
        file_info = FileInfo(
            filename=disk_path.name,
            original_path=original_name,
            stored_path=str(disk_path),
            size_bytes=disk_path.stat().st_size,
            file_type=file_type,
            mime_hint=mime_hint,
        )
        job.files.append(file_info)


def delete_job(job_id: str) -> bool:
    """Delete a job and its files from disk."""
    job = _jobs.pop(job_id, None)
    if job is None:
        return False

    job_dir = settings.UPLOAD_DIR / job_id
    if job_dir.exists():
        shutil.rmtree(job_dir)
    return True


def _extract_zip(
    zip_path: Path, job_dir: Path, job: Job
) -> list[tuple[Path, str]]:
    """
    Extract a zip archive into the job directory.

    Returns list of (disk_path, original_path_in_zip) for each extracted file.
    Skips directories and handles nested folder structures.
    """
    extracted: list[tuple[Path, str]] = []

    try:
        with zipfile.ZipFile(zip_path, "r") as zf:
            for member in zf.infolist():
                # Skip directories
                if member.is_dir():
                    continue

                # Skip hidden/OS files
                name = member.filename
                if any(
                    part.startswith(".") or part.lower() == "__macosx"
                    for part in Path(name).parts
                ):
                    continue

                # Extract preserving structure under job_dir
                target = job_dir / name
                target.parent.mkdir(parents=True, exist_ok=True)

                with zf.open(member) as src, open(target, "wb") as dst:
                    dst.write(src.read())

                extracted.append((target, name))

    except zipfile.BadZipFile:
        job.errors.append(f"'{zip_path.name}' is not a valid zip archive")
    except Exception as e:
        job.errors.append(f"Error extracting '{zip_path.name}': {e}")

    return extracted
