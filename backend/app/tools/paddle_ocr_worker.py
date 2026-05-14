from __future__ import annotations

import json
import sys
from pathlib import Path

from paddleocr import PaddleOCR


def build_ocr() -> PaddleOCR:
    return PaddleOCR(
        use_doc_orientation_classify=False,
        use_doc_unwarping=False,
        use_textline_orientation=False,
        lang="ch",
    )


def polygon_to_bbox(points) -> list[int]:
    xs = [int(point[0]) for point in points]
    ys = [int(point[1]) for point in points]
    min_x = min(xs)
    min_y = min(ys)
    max_x = max(xs)
    max_y = max(ys)
    return [min_x, min_y, max_x - min_x, max_y - min_y]


def main() -> int:
    payload = json.loads(sys.stdin.read() or "{}")
    pages = payload.get("pages", [])
    if not isinstance(pages, list):
        raise RuntimeError("Invalid paddle OCR payload.")

    ocr = build_ocr()
    results: list[dict] = []
    for page in pages:
        page_number = int(page["page"])
        image_path = Path(page["image_path"])
        prediction = ocr.predict(str(image_path))[0]
        rec_texts = prediction["rec_texts"]
        rec_scores = prediction["rec_scores"]
        rec_polys = prediction["rec_polys"]
        lines: list[dict] = []
        for index, text in enumerate(rec_texts, start=1):
            normalized = str(text or "").strip()
            if not normalized:
                continue
            score = float(rec_scores[index - 1])
            bbox = polygon_to_bbox(rec_polys[index - 1])
            lines.append(
                {
                    "id": f"paddle_{page_number:03d}_{index:03d}",
                    "text": normalized,
                    "bbox": bbox,
                    "score": score,
                }
            )

        lines.sort(key=lambda item: (item["bbox"][1], item["bbox"][0]))
        average_score = sum(item["score"] for item in lines) / len(lines) if lines else 0.0
        results.append(
            {
                "page": page_number,
                "lines": lines,
                "average_score": round(average_score, 6),
            }
        )

    sys.stdout.buffer.write(json.dumps({"pages": results}, ensure_ascii=False).encode("utf-8"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
