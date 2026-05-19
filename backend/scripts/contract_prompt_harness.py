from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.agents.contract_parser_agent import ContractParserAgent
from app.config import get_settings
from app.data.default_relations import build_default_relations
from app.services.document_service import DocumentService
from app.services.ocr_service import OCRService
from app.services.paddle_ocr_service import PaddleOCRService
from app.services.qwen_service import QwenService


async def main() -> None:
    parser = argparse.ArgumentParser(description="Run prompt harness for contract parsing.")
    parser.add_argument("--file", type=str, required=True, help="Absolute path to the contract file.")
    parser.add_argument("--output", type=str, default="", help="Optional JSON output path.")
    args = parser.parse_args()

    file_path = Path(args.file).resolve()
    if not file_path.exists():
        raise SystemExit(f"File not found: {file_path}")

    settings = get_settings()
    qwen_service = QwenService(settings)
    paddle_service = PaddleOCRService(
        python_executable=settings.paddle_python_executable,
        timeout_seconds=settings.paddle_ocr_timeout_seconds,
        batch_size=settings.paddle_ocr_batch_size,
    )
    ocr_service = OCRService(settings=settings, qwen_service=qwen_service, paddle_ocr_service=paddle_service)
    document_service = DocumentService()
    parser_agent = ContractParserAgent(qwen_service=qwen_service, settings=settings)
    relations = build_default_relations()

    preparation = document_service.prepare(
        file_name=file_path.name,
        file_path=file_path,
        use_builtin_example=False,
    )
    extracted = await ocr_service.extract_document(
        task_id=f"harness_{file_path.stem}",
        preparation=preparation,
        output_root=ROOT / settings.storage_dir,
    )
    sections = await parser_agent.reconstruct_sections(extracted.pages)
    clauses = await parser_agent.identify_clauses(extracted.pages, sections, relations)
    key_facts = await parser_agent.extract_key_facts(extracted.pages, clauses, relations)

    payload = {
        "file": str(file_path),
        "pipeline": extracted.pipeline,
        "warnings": extracted.warnings,
        "pages": len(extracted.pages),
        "sections": [section.model_dump() for section in sections],
        "clauses": [clause.model_dump() for clause in clauses],
        "keyFacts": [fact.model_dump() for fact in key_facts],
    }

    output_path = Path(args.output).resolve() if args.output else ROOT / "debug" / f"{file_path.stem}.prompt-harness.json"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    print(json.dumps({
        "file": str(file_path),
        "output": str(output_path),
        "pipeline": extracted.pipeline,
        "pageCount": len(extracted.pages),
        "sectionCount": len(sections),
        "clauseCount": len(clauses),
        "keyFactCount": len(key_facts),
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    asyncio.run(main())
