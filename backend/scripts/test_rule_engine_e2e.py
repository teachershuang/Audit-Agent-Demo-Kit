from __future__ import annotations

import argparse
import json
import sys
import time
from copy import deepcopy
from datetime import datetime
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.logging_utils import get_run_logs_dir


def write_log(name: str, payload: dict) -> Path:
    logs_dir = get_run_logs_dir()
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    path = logs_dir / f"{name}-{timestamp}.json"
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    return path


def append_missing_rule_config(configs: list[dict]) -> list[dict]:
    result = deepcopy(configs)
    result.append(
        {
            "id": "rule_missing_demo",
            "name": "不存在的规则演示",
            "description": "用于测试规则配置存在但规则引擎里没有对应 ruleId 的情况。",
            "enabled": True,
            "riskPrompt": "验证规则引擎配置失配提示。",
            "toolSource": ["rule_engine_future"],
            "priority": "medium",
            "configType": "rule_check",
            "rulePayload": {
                "ruleId": "rule_not_uploaded_to_engine",
                "severity": "medium",
                "extractFields": [
                    {"label": "付款条件", "description": "提取付款条件用于失配测试"},
                ],
            },
        }
    )
    return result


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--backend-base", default="http://127.0.0.1:8010")
    parser.add_argument("--file", default="C:/Users/26423/Desktop/15-20220929技术服务合同.pdf")
    parser.add_argument("--timeout", type=int, default=900)
    args = parser.parse_args()

    backend_base = args.backend_base.rstrip("/")
    file_path = Path(args.file)
    if not file_path.exists():
        raise SystemExit(f"file not found: {file_path}")

    transport = httpx.HTTPTransport(retries=0)
    with httpx.Client(base_url=backend_base, timeout=60, transport=transport, trust_env=False) as client:
        with file_path.open("rb") as fh:
            upload_response = client.post(
                "/api/contracts/upload",
                files={"file": (file_path.name, fh, "application/pdf")},
                data={"use_builtin_example": "false"},
            )
        upload_response.raise_for_status()
        upload_payload = upload_response.json()
        task_id = upload_payload["task_id"]

        analyze_response = client.post(f"/api/contracts/{task_id}/analyze")
        analyze_response.raise_for_status()
        analyze_payload = analyze_response.json()

        started = time.time()
        final_task = None
        while time.time() - started < args.timeout:
            task_response = client.get(f"/api/contracts/{task_id}")
            task_response.raise_for_status()
            final_task = task_response.json()
            if final_task.get("status") != "processing":
                break
            time.sleep(2)
        if not final_task or final_task.get("status") == "processing":
            raise TimeoutError(f"task {task_id} did not finish within {args.timeout}s")

        result_response = client.get(f"/api/contracts/{task_id}/result")
        result_response.raise_for_status()
        result_payload = result_response.json()

        final_artifacts_response = client.post(f"/api/contracts/{task_id}/analyze")
        final_artifacts_response.raise_for_status()
        final_artifacts = final_artifacts_response.json()

        configs_response = client.get("/api/config/audit-configs")
        configs_response.raise_for_status()
        configs_payload = configs_response.json()

        default_rules_response = client.post(
            "/api/rules/evaluate-task",
            json={"task_id": task_id, "trace": False},
        )
        default_rules_response.raise_for_status()
        default_rule_payload = default_rules_response.json()

        mismatch_rules_response = client.post(
            "/api/rules/evaluate-task",
            json={"task_id": task_id, "relations": append_missing_rule_config(configs_payload), "trace": False},
        )
        mismatch_rules_response.raise_for_status()
        mismatch_rule_payload = mismatch_rules_response.json()

        output_path = write_log(
            "rule-engine-e2e",
            {
                "backendBase": backend_base,
                "file": str(file_path),
                "taskId": task_id,
                "upload": upload_payload,
                "initialAnalyze": analyze_payload,
                "finalTask": final_task,
                "resultCounts": {
                    "pages": len(result_payload.get("pages") or []),
                    "sections": len(result_payload.get("sections") or []),
                    "clauses": len(result_payload.get("clauses") or []),
                    "keyFacts": len(result_payload.get("keyFacts") or []),
                },
                "finalArtifactsCounts": {
                    "auditFocuses": len(final_artifacts.get("auditFocuses") or []),
                    "verificationItems": len(final_artifacts.get("verificationItems") or []),
                    "agentSteps": len(final_artifacts.get("agentSteps") or []),
                },
                "defaultRuleEval": default_rule_payload,
                "mismatchRuleEval": mismatch_rule_payload,
            },
        )
        print(output_path)


if __name__ == "__main__":
    main()
