from __future__ import annotations

import asyncio
import base64
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx

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
    def __init__(
        self,
        python_executable: str,
        timeout_seconds: int,
        batch_size: int = 3,
        *,
        mode: str = "local_subprocess",
        remote_base_url: str = "",
        remote_endpoint: str = "/ocr",
        remote_health_path: str = "/health",
        remote_timeout_seconds: int = 8,
    ) -> None:
        self.python_executable = Path(python_executable)
        self.timeout_seconds = timeout_seconds
        self.batch_size = max(1, batch_size)
        self.worker_script = Path(__file__).resolve().parents[1] / "tools" / "paddle_ocr_worker.py"
        self.mode = mode
        self.remote_base_url = remote_base_url
        self.remote_endpoint = remote_endpoint
        self.remote_health_path = remote_health_path
        self.remote_timeout_seconds = remote_timeout_seconds

    def configure(
        self,
        *,
        mode: str | None = None,
        remote_base_url: str | None = None,
        remote_endpoint: str | None = None,
        remote_health_path: str | None = None,
    ) -> None:
        if mode is not None:
            self.mode = mode
        if remote_base_url is not None:
            self.remote_base_url = remote_base_url
        if remote_endpoint is not None:
            self.remote_endpoint = remote_endpoint
        if remote_health_path is not None:
            self.remote_health_path = remote_health_path

    @property
    def local_available(self) -> bool:
        return self.python_executable.exists() and self.worker_script.exists()

    @property
    def remote_available(self) -> bool:
        return bool(self.remote_base_url)

    @property
    def is_available(self) -> bool:
        mode = (self.mode or "local_subprocess").strip().lower()
        if mode == "remote_http":
            return self.remote_available
        if mode == "remote_first":
            return self.remote_available or self.local_available
        return self.local_available

    async def probe_health(self) -> dict[str, Any]:
        mode = (self.mode or "local_subprocess").strip().lower()
        if mode == "local_subprocess":
            return {
                "mode": mode,
                "available": self.local_available,
                "provider": str(self.python_executable),
                "status": "ok" if self.local_available else "not_available",
            }
        if not self.remote_base_url:
            return {
                "mode": mode,
                "available": False,
                "provider": None,
                "status": "not_configured",
            }
        health_url = f"{self.remote_base_url.rstrip('/')}{self.remote_health_path}"
        try:
            async with httpx.AsyncClient(timeout=4, trust_env=False) as client:
                response = await client.get(health_url)
                response.raise_for_status()
                payload = response.json()
            return {
                "mode": mode,
                "available": True,
                "provider": self.remote_base_url,
                "status": "ok",
                "raw": payload,
            }
        except Exception as exc:
            return {
                "mode": mode,
                "available": False,
                "provider": self.remote_base_url,
                "status": "probe_failed",
                "error": str(exc),
            }

    async def extract_pages(self, pages: list[dict[str, object]]) -> dict[int, list[PaddleOCRLine]]:
        if not pages:
            return {}
        mode = (self.mode or "local_subprocess").strip().lower()
        if mode == "remote_http":
            return await self._extract_pages_remote(pages)
        if mode == "remote_first":
            try:
                return await self._extract_pages_remote(pages)
            except Exception as exc:
                app_logger.warning(
                    json_dumps(
                        {
                            "event": "paddle_remote_failed_fallback_local",
                            "error": str(exc),
                            "remoteBaseUrl": self.remote_base_url,
                            "pageCount": len(pages),
                        }
                    )
                )
                return await self._extract_pages_local(pages)
        return await self._extract_pages_local(pages)

    async def _extract_pages_local(self, pages: list[dict[str, object]]) -> dict[int, list[PaddleOCRLine]]:
        if not self.local_available:
            raise RuntimeError(f"Paddle OCR runtime is not available: {self.python_executable}")
        results: dict[int, list[PaddleOCRLine]] = {}
        for batch_index, batch in enumerate(self._chunk_pages(pages), start=1):
            batch_results = await self._extract_local_batch(batch=batch, batch_index=batch_index)
            results.update(batch_results)
        return results

    async def _extract_local_batch(
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
                    "mode": "local_subprocess",
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
        results = self._parse_remote_style_pages(data)
        app_logger.info(
            json_dumps(
                {
                    "event": "paddle_ocr_batch_completed",
                    "mode": "local_subprocess",
                    "pageCount": len(results),
                    "pages": sorted(results),
                    "batchIndex": batch_index,
                    "stderrSummary": stderr_text[:300] if stderr_text else None,
                }
            )
        )
        return results

    async def _extract_pages_remote(self, pages: list[dict[str, object]]) -> dict[int, list[PaddleOCRLine]]:
        if not self.remote_base_url:
            raise RuntimeError("Remote Paddle OCR base URL is not configured.")

        results: dict[int, list[PaddleOCRLine]] = {}
        for batch_index, batch in enumerate(self._chunk_pages(pages), start=1):
            for page in batch:
                page_number = int(page["page"])
                image_path = str(page["image_path"])
                page_result = await self._extract_remote_single_page(page_number=page_number, image_path=image_path)
                results[page_number] = page_result
            app_logger.info(
                json_dumps(
                    {
                        "event": "paddle_ocr_batch_completed",
                        "mode": "remote_http",
                        "pageCount": len(batch),
                        "pages": [int(item["page"]) for item in batch],
                        "batchIndex": batch_index,
                        "remoteBaseUrl": self.remote_base_url,
                    }
                )
            )
        return results

    async def _extract_remote_single_page(self, *, page_number: int, image_path: str) -> list[PaddleOCRLine]:
        image_bytes = Path(image_path).read_bytes()
        image_b64 = base64.b64encode(image_bytes).decode("utf-8")
        request_candidates = [
            {"image_base64": image_b64},
            {"image": image_b64},
            {"images": [image_b64]},
            {"page": page_number, "image_base64": image_b64},
            {"page": page_number, "image": image_b64},
            {"pages": [{"page": page_number, "image_base64": image_b64}]},
            {"pages": [{"page": page_number, "image": image_b64}]},
        ]
        errors: list[str] = []
        for candidate in request_candidates:
            try:
                data = await self._post_remote_ocr(candidate)
                parsed = self._parse_remote_ocr_payload(data, page_number=page_number)
                if parsed:
                    return parsed
            except Exception as exc:
                errors.append(str(exc))
                continue
        raise RuntimeError(
            "Remote Paddle OCR request failed for all known payload shapes. "
            f"page={page_number}, errors={errors[:3]}"
        )

    async def _post_remote_ocr(self, payload: dict[str, Any]) -> dict[str, Any]:
        url = f"{self.remote_base_url.rstrip('/')}{self.remote_endpoint}"
        async with httpx.AsyncClient(timeout=self.remote_timeout_seconds, trust_env=False) as client:
            response = await client.post(url, json=payload)
            if response.is_error:
                raise RuntimeError(f"remote_http {response.status_code}: {response.text[:200]}")
            return response.json()

    def _parse_remote_ocr_payload(self, data: dict[str, Any], *, page_number: int) -> list[PaddleOCRLine]:
        if "pages" in data:
            return self._parse_remote_style_pages(data).get(page_number, [])
        candidates = (
            data.get("lines"),
            data.get("result"),
            data.get("data"),
            data.get("items"),
        )
        for candidate in candidates:
            parsed = self._parse_line_collection(candidate, page_number=page_number)
            if parsed:
                return parsed
        return []

    def _parse_remote_style_pages(self, data: dict[str, Any]) -> dict[int, list[PaddleOCRLine]]:
        results: dict[int, list[PaddleOCRLine]] = {}
        for page_result in data.get("pages", []):
            page_number = int(page_result["page"])
            parsed = self._parse_line_collection(page_result.get("lines", []), page_number=page_number)
            results[page_number] = parsed
        return results

    def _parse_line_collection(self, collection: Any, *, page_number: int) -> list[PaddleOCRLine]:
        if isinstance(collection, dict):
            if "lines" in collection:
                return self._parse_line_collection(collection.get("lines"), page_number=page_number)
            if "items" in collection:
                return self._parse_line_collection(collection.get("items"), page_number=page_number)
            return []
        if not isinstance(collection, list):
            return []
        lines: list[PaddleOCRLine] = []
        for index, item in enumerate(collection, start=1):
            if not isinstance(item, dict):
                continue
            bbox = item.get("bbox") or item.get("box") or item.get("rect") or [0, 0, 0, 0]
            if isinstance(bbox, list) and len(bbox) == 4 and all(isinstance(v, (int, float)) for v in bbox):
                x, y, width, height = int(bbox[0]), int(bbox[1]), int(bbox[2]), int(bbox[3])
            elif isinstance(bbox, list) and len(bbox) >= 4 and all(isinstance(v, list) and len(v) >= 2 for v in bbox):
                xs = [point[0] for point in bbox]
                ys = [point[1] for point in bbox]
                x = int(min(xs))
                y = int(min(ys))
                width = int(max(xs) - min(xs))
                height = int(max(ys) - min(ys))
            else:
                x = y = 0
                width = height = 0
            text = str(item.get("text") or item.get("content") or item.get("value") or "").strip()
            if not text:
                continue
            lines.append(
                PaddleOCRLine(
                    id=str(item.get("id") or f"remote_paddle_{page_number:03d}_{index:03d}"),
                    text=text,
                    x=x,
                    y=y,
                    width=max(1, width),
                    height=max(1, height),
                    score=float(item.get("score") or item.get("confidence") or 0.0),
                )
            )
        lines.sort(key=lambda line: (line.y, line.x))
        return lines

    def _chunk_pages(self, pages: list[dict[str, object]]) -> list[list[dict[str, object]]]:
        if len(pages) <= max(12, self.batch_size * 2):
            return [pages]
        return [pages[index : index + self.batch_size] for index in range(0, len(pages), self.batch_size)]
