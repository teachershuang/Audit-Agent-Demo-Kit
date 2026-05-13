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
    use_builtin_example: bool = False


class DocumentService:
    def prepare(
        self,
        file_name: str,
        file_path: Path | None,
        use_builtin_example: bool,
    ) -> DocumentPreparation:
        suffix = Path(file_name).suffix.lower()
        if suffix == ".pdf":
            file_type = "pdf"
        elif suffix in {".png", ".jpg", ".jpeg"}:
            file_type = "image"
        else:
            file_type = "unknown"

        is_scanned = file_type == "image"
        if use_builtin_example:
            pipeline = "builtin-example"
        elif file_type == "pdf":
            pipeline = "pdf"
        elif file_type == "image":
            pipeline = "image"
        else:
            pipeline = "unsupported"

        return DocumentPreparation(
            file_name=file_name,
            file_type=file_type,
            is_scanned=is_scanned,
            recommended_pipeline=pipeline,
            source_path=file_path,
            use_builtin_example=use_builtin_example,
        )
