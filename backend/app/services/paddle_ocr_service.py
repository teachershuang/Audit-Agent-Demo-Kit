from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass
from pathlib import Path

from app.logging_utils import app_logger, json_dumps


@dataclass
class PaddleOCRLine:
    id: str
    text: str
    x: int
    y: int
    width: int
    height: int
    score: float


class PaddleOCRService:
    def __init__(self, python_executable: str, timeout_seconds: int, batch_size: int = 3) -> None:
        self.python_executable = Path(python_executable)
        self.timeout_seconds = timeout_seconds
        self.batch_size = max(1, batch_size)
        self.worker_script = Path(__file__).resolve().parents[1] / "tools" / "paddle_ocr_worker.py"

    @property
    def is_available(self) -> bool:
        return self.python_executable.exists() and self.worker_script.exists()

    async def extract_pages(self, pages: list[dict[str, object]]) -> dict[int, list[PaddleOCRLine]]:
        if not self.is_available:
            raise RuntimeError(f"Paddle OCR runtime is not available: {self.python_executable}")
        if not pages:
            return {}

        results: dict[int, list[PaddleOCRLine]] = {}
        for batch_index, batch in enumerate(self._chunk_pages(pages), start=1):
            batch_results = await self._extract_batch(batch=batch, batch_index=batch_index)
            results.update(batch_results)
        return results

    async def _extract_batch(
        self,
        batch: list[dict[str, object]],
        batch_index: int,
    ) -> dict[int, list[PaddleOCRLine]]:
        payload = json.dumps({"pages": batch}, ensure_ascii=False)
        page_numbers = [int(item["page"]) for item in batch]

        app_logger.info(
            json_dumps(
                {
                    "event": "paddle_ocr_batch_started",
                    "pageCount": len(batch),
                    "pages": page_numbers,
                    "batchIndex": batch_index,
                    "pythonExecutable": str(self.python_executable),
                }
            )
        )

        process = await asyncio.create_subprocess_exec(
            str(self.python_executable),
            str(self.worker_script),
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        try:
            stdout, stderr = await asyncio.wait_for(process.communicate(payload.encode("utf-8")), timeout=self.timeout_seconds)
        except asyncio.TimeoutError as exc:
            process.kill()
            await process.communicate()
            raise RuntimeError(f"Paddle OCR timed out after {self.timeout_seconds} seconds.") from exc

        stderr_text = stderr.decode("utf-8", errors="ignore").strip()
        if process.returncode != 0:
            raise RuntimeError(stderr_text or f"Paddle OCR worker exited with code {process.returncode}.")

        raw = stdout.decode("utf-8", errors="ignore").strip()
        data = json.loads(raw or "{}")
        results: dict[int, list[PaddleOCRLine]] = {}
        for page_result in data.get("pages", []):
            page_number = int(page_result["page"])
            lines: list[PaddleOCRLine] = []
            for item in page_result.get("lines", []):
                bbox = item.get("bbox") or [0, 0, 0, 0]
                lines.append(
                    PaddleOCRLine(
                        id=str(item["id"]),
                        text=str(item["text"]).strip(),
                        x=int(bbox[0]),
                        y=int(bbox[1]),
                        width=max(1, int(bbox[2])),
                        height=max(1, int(bbox[3])),
                        score=float(item.get("score", 0.0)),
                    )
                )
            lines.sort(key=lambda line: (line.y, line.x))
            results[page_number] = lines

        app_logger.info(
            json_dumps(
                {
                    "event": "paddle_ocr_batch_completed",
                    "pageCount": len(results),
                    "pages": sorted(results),
                    "batchIndex": batch_index,
                    "stderrSummary": stderr_text[:300] if stderr_text else None,
                }
            )
        )
        return results

    def _chunk_pages(self, pages: list[dict[str, object]]) -> list[list[dict[str, object]]]:
        if len(pages) <= max(12, self.batch_size * 2):
            return [pages]
        return [pages[index : index + self.batch_size] for index in range(0, len(pages), self.batch_size)]
