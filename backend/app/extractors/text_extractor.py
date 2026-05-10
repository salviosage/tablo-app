"""
Text extractor — reads freeform text files (notes, emails, etc).

Simple but important: notes.txt contains context that the reconciliation
engine uses to flag personal charges, match refunds, and extract action items.
"""

from __future__ import annotations

from pathlib import Path

from app.models.schemas import ExtractedNotes


def extract_text(file_path: str) -> tuple[ExtractedNotes, list[str]]:
    """
    Read a text file and return its contents.

    Returns:
        (notes, warnings)
    """
    warnings: list[str] = []
    path = Path(file_path)

    try:
        raw = path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        try:
            raw = path.read_text(encoding="latin-1")
            warnings.append(
                f"Text '{path.name}': read with latin-1 fallback encoding")
        except Exception as e:
            warnings.append(f"Text: couldn't read '{path.name}': {e}")
            return ExtractedNotes(source_file=path.name), warnings
    except Exception as e:
        warnings.append(f"Text: couldn't read '{path.name}': {e}")
        return ExtractedNotes(source_file=path.name), warnings

    lines = [line.strip() for line in raw.split("\n") if line.strip()]

    return ExtractedNotes(
        raw_text=raw,
        lines=lines,
        source_file=path.name,
    ), warnings
