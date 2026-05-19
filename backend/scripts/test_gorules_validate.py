from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path

import httpx


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://192.168.3.7:8999")
    parser.add_argument("--input", default=str(Path(__file__).resolve().parents[2] / "docs" / "gorules-request.example.json"))
    parser.add_argument("--trace", action="store_true")
    args = parser.parse_args()

    input_path = Path(args.input)
    payload = json.loads(input_path.read_text(encoding="utf-8"))
    request_body = {"payload": payload, "trace": args.trace}

    log_dir = Path(__file__).resolve().parents[2] / ".run-logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    request_log = log_dir / f"gorules-request-{stamp}.json"
    response_log = log_dir / f"gorules-response-{stamp}.json"
    request_log.write_text(json.dumps(request_body, ensure_ascii=False, indent=2), encoding="utf-8")

    with httpx.Client(timeout=60, trust_env=False) as client:
        response = client.post(f"{args.base_url.rstrip('/')}/validate", json=request_body)
        response.raise_for_status()
        data = response.json()

    response_log.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"requestLog": str(request_log), "responseLog": str(response_log)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
