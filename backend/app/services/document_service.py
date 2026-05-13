from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass
class DocumentPreparation:
    file_name: str
    file_type: str
    is_scanned: bool
    recommended_pipeline: str
    source_path: Path | None = None


class DocumentService:
    def prepare(self, file_name: str, file_path: Path | None, use_sample: bool) -> DocumentPreparation:
        suffix = Path(file_name).suffix.lower()
        if suffix == ".pdf":
            file_type = "pdf"
        elif suffix in {".png", ".jpg", ".jpeg"}:
            file_type = "image"
        else:
            file_type = "unknown"

        is_scanned = file_type == "image"
        if file_type == "pdf":
            recommended_pipeline = "text-extract-first"
        elif file_type == "image":
            recommended_pipeline = "ocr-first"
        else:
            recommended_pipeline = "mock-fallback"

        if use_sample:
            recommended_pipeline = "mock-sample"

        return DocumentPreparation(
            file_name=file_name,
            file_type=file_type,
            is_scanned=is_scanned,
            recommended_pipeline=recommended_pipeline,
            source_path=file_path,
        )
