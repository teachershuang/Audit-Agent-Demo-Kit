from __future__ import annotations

import argparse
import hashlib
import html
import json
import os
import subprocess
import time
from collections import Counter
from dataclasses import dataclass
from datetime import datetime
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any

import fitz
import httpx


ROOT = Path(__file__).resolve().parents[2]
UPLOADS_DIR = ROOT / "backend" / "uploads"
TASKS_DIR = UPLOADS_DIR / "tasks"
DEFAULT_API_BASE = "http://127.0.0.1:8010"
DEFAULT_OUTPUT = ROOT / "output" / "comparison"


@dataclass
class ProfileRun:
    profile_id: str
    profile_label: str
    task_id: str
    task_payload: dict[str, Any]
    result_payload: dict[str, Any]
    elapsed_ms: int
    runtime_snapshot: dict[str, Any]


def find_contract_path(explicit: str | None) -> Path:
    if explicit:
        path = Path(explicit)
        if path.exists():
            return path
        raise FileNotFoundError(f"Contract file not found: {explicit}")

    for path in UPLOADS_DIR.rglob("*.pdf"):
        if "15-20220929" in path.name:
            return path
    raise FileNotFoundError("Could not find 15-20220929 technical service contract PDF.")


def switch_profile(client: httpx.Client, profile_id: str) -> dict[str, Any]:
    response = client.post(
        "/api/runtime/model-profiles/switch",
        json={"profile_id": profile_id},
        timeout=60,
    )
    response.raise_for_status()
    return response.json()


def upload_contract(client: httpx.Client, contract_path: Path) -> str:
    with contract_path.open("rb") as file_obj:
        response = client.post(
            "/api/contracts/upload",
            files={"file": (contract_path.name, file_obj, "application/pdf")},
            timeout=120,
        )
    response.raise_for_status()
    payload = response.json()
    return payload["task_id"]


def start_analysis(client: httpx.Client, task_id: str) -> None:
    response = client.post(f"/api/contracts/{task_id}/analyze", timeout=120)
    response.raise_for_status()


def poll_task(client: httpx.Client, task_id: str, timeout_seconds: int) -> dict[str, Any]:
    deadline = time.time() + timeout_seconds
    last_payload: dict[str, Any] | None = None
    while time.time() < deadline:
        response = client.get(f"/api/contracts/{task_id}", timeout=30)
        response.raise_for_status()
        last_payload = response.json()
        status = last_payload.get("status")
        kb = last_payload.get("knowledgeBaseReview") or {}
        kb_status = kb.get("status")
        if status in {"completed", "needs_review"} and kb_status in {None, "idle", "completed", "failed"}:
            return last_payload
        time.sleep(5)
    if last_payload is None:
        raise TimeoutError(f"Task {task_id} did not return any polling payload.")
    return last_payload


def fetch_result(client: httpx.Client, task_id: str) -> dict[str, Any]:
    response = client.get(f"/api/contracts/{task_id}/result", timeout=60)
    response.raise_for_status()
    return response.json()


def load_task_file(task_id: str) -> dict[str, Any]:
    path = TASKS_DIR / f"{task_id}.json"
    if not path.exists():
        raise FileNotFoundError(f"Persisted task file not found: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as file_obj:
        for chunk in iter(lambda: file_obj.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def git_commit() -> str:
    try:
        return subprocess.check_output(["git", "rev-parse", "--short", "HEAD"], cwd=ROOT, text=True).strip()
    except Exception:
        return "unknown"


def env_value(name: str, default: str = "unknown") -> str:
    if os.getenv(name):
        return str(os.getenv(name))
    env_path = ROOT / ".env"
    if not env_path.exists():
        return default
    for line in env_path.read_text(encoding="utf-8").splitlines():
        if not line or line.lstrip().startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        if key.strip() == name:
            return value.strip()
    return default


def run_profile(
    client: httpx.Client,
    contract_path: Path,
    profile_id: str,
    timeout_seconds: int,
) -> ProfileRun:
    runtime_snapshot = switch_profile(client, profile_id)
    task_id = upload_contract(client, contract_path)
    start_analysis(client, task_id)
    poll_task(client, task_id, timeout_seconds=timeout_seconds)
    result_payload = fetch_result(client, task_id)
    task_payload = load_task_file(task_id)
    return ProfileRun(
        profile_id=profile_id,
        profile_label=runtime_snapshot.get("currentProfileLabel") or profile_id,
        task_id=task_id,
        task_payload=task_payload,
        result_payload=result_payload,
        elapsed_ms=(result_payload.get("task") or {}).get("elapsedMs") or 0,
        runtime_snapshot=runtime_snapshot,
    )


def load_profile_run_from_task(task_id: str, profile_id: str) -> ProfileRun:
    task_payload = load_task_file(task_id)
    result_payload = task_payload.get("result")
    if not isinstance(result_payload, dict):
        raise ValueError(f"Task {task_id} has no persisted result.")
    task = result_payload.get("task") or task_payload.get("task") or {}
    model_name = task.get("modelName") or profile_id
    runtime_snapshot = {
        "currentProfileId": profile_id,
        "currentProfileLabel": profile_id,
        "profiles": [
            {
                "id": profile_id,
                "label": profile_id,
                "textModel": model_name,
                "visionModel": "qwen-vl-plus" if profile_id == "public" else None,
                "reviewModel": model_name,
                "ocrStrategy": "paddle_primary",
                "enableVlOcrEnhancement": profile_id == "public",
            }
        ],
    }
    return ProfileRun(
        profile_id=profile_id,
        profile_label=profile_id,
        task_id=task_id,
        task_payload=task_payload,
        result_payload=result_payload,
        elapsed_ms=task.get("elapsedMs") or 0,
        runtime_snapshot=runtime_snapshot,
    )


def extract_page_text(page: dict[str, Any]) -> str:
    blocks = page.get("blocks") or []
    parts = []
    for block in blocks:
        text = str(block.get("text") or "").strip()
        if text:
            parts.append(text)
    return "\n".join(parts)


def normalize_text(text: str) -> str:
    return "".join(ch for ch in text if not ch.isspace())


def matching_chars(a: str, b: str) -> int:
    matcher = SequenceMatcher(a=a, b=b)
    total = 0
    for block in matcher.get_matching_blocks():
        total += block.size
    return total


def build_page_comparison(public_pages: list[dict[str, Any]], local_pages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    max_pages = max(len(public_pages), len(local_pages))
    comparisons: list[dict[str, Any]] = []
    for index in range(max_pages):
        public_page = public_pages[index] if index < len(public_pages) else {}
        local_page = local_pages[index] if index < len(local_pages) else {}
        public_text = normalize_text(extract_page_text(public_page))
        local_text = normalize_text(extract_page_text(local_page))
        matched = matching_chars(public_text[:5000], local_text[:5000])
        similarity = SequenceMatcher(a=public_text[:5000], b=local_text[:5000]).ratio() if public_text or local_text else 1.0
        public_len = len(public_text)
        local_len = len(local_text)
        comparisons.append(
            {
                "page": index + 1,
                "public_chars": public_len,
                "local_chars": local_len,
                "matched_chars": matched,
                "similarity": similarity,
                "local_missing_vs_public": max(public_len - matched, 0),
                "public_missing_vs_local": max(local_len - matched, 0),
                "public_blocks": len(public_page.get("blocks") or []),
                "local_blocks": len(local_page.get("blocks") or []),
                "public_preview": extract_page_text(public_page)[:260],
                "local_preview": extract_page_text(local_page)[:260],
            }
        )
    return comparisons


def build_section_comparison(public_sections: list[dict[str, Any]], local_sections: list[dict[str, Any]]) -> dict[str, Any]:
    def is_major(item: dict[str, Any]) -> bool:
        code = str(item.get("sectionCode") or "")
        if code.startswith(("（", "(")):
            return False
        return item.get("level") == 1 or code.startswith("第")

    public_major = [item for item in public_sections if is_major(item)]
    local_major = [item for item in local_sections if is_major(item)]
    public_titles = [f"{item.get('sectionCode') or ''} {item.get('title') or ''}".strip() for item in public_major]
    local_titles = [f"{item.get('sectionCode') or ''} {item.get('title') or ''}".strip() for item in local_major]
    public_set = set(public_titles)
    local_set = set(local_titles)
    return {
        "public_count": len(public_major),
        "local_count": len(local_major),
        "public_total_count": len(public_sections),
        "local_total_count": len(local_sections),
        "public_child_count": max(len(public_sections) - len(public_major), 0),
        "local_child_count": max(len(local_sections) - len(local_major), 0),
        "missing_in_local": [title for title in public_titles if title not in local_set][:20],
        "extra_in_local": [title for title in local_titles if title not in public_set][:20],
        "public_titles": public_titles,
        "local_titles": local_titles,
    }


def build_clause_comparison(public_clauses: list[dict[str, Any]], local_clauses: list[dict[str, Any]]) -> dict[str, Any]:
    public_core = [item.get("coreLabel") or item.get("label") or "" for item in public_clauses]
    local_core = [item.get("coreLabel") or item.get("label") or "" for item in local_clauses]
    public_counter = Counter(public_core)
    local_counter = Counter(local_core)
    labels = sorted(set(public_counter) | set(local_counter))
    rows = []
    for label in labels:
        rows.append(
            {
                "label": label,
                "public_count": public_counter.get(label, 0),
                "local_count": local_counter.get(label, 0),
                "delta": local_counter.get(label, 0) - public_counter.get(label, 0),
            }
        )
    return {
        "public_count": len(public_clauses),
        "local_count": len(local_clauses),
        "rows": rows,
    }


def build_key_fact_comparison(public_facts: list[dict[str, Any]], local_facts: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_label_public: dict[str, list[dict[str, Any]]] = {}
    by_label_local: dict[str, list[dict[str, Any]]] = {}
    for item in public_facts:
        by_label_public.setdefault(item.get("label") or "未命名字段", []).append(item)
    for item in local_facts:
        by_label_local.setdefault(item.get("label") or "未命名字段", []).append(item)

    labels = sorted(set(by_label_public) | set(by_label_local))
    rows = []
    for label in labels:
        public_values = [item.get("value") or "" for item in by_label_public.get(label, [])]
        local_values = [item.get("value") or "" for item in by_label_local.get(label, [])]
        rows.append(
            {
                "label": label,
                "public_value": "；".join(public_values[:3]) or "未提取",
                "local_value": "；".join(local_values[:3]) or "未提取",
                "same": (public_values[:1] == local_values[:1]) if public_values or local_values else True,
            }
        )
    return rows


def summarize_verification(items: list[dict[str, Any]]) -> dict[str, int]:
    counter = Counter(item.get("status") or "unknown" for item in items)
    return dict(counter)


def summarize_audit_sources(items: list[dict[str, Any]]) -> dict[str, int]:
    counter = Counter(item.get("focusSource") or "unknown" for item in items)
    return dict(counter)


def extract_step_map(task_payload: dict[str, Any]) -> dict[str, dict[str, Any]]:
    rows = task_payload.get("agent_steps") or []
    return {row.get("name") or row.get("id") or f"step_{index}": row for index, row in enumerate(rows, start=1)}


def build_step_comparison(public_task: dict[str, Any], local_task: dict[str, Any]) -> list[dict[str, Any]]:
    public_map = extract_step_map(public_task)
    local_map = extract_step_map(local_task)
    names = list(dict.fromkeys(list(public_map.keys()) + list(local_map.keys())))
    rows = []
    for name in names:
        public_step = public_map.get(name, {})
        local_step = local_map.get(name, {})
        rows.append(
            {
                "name": name,
                "public_status": public_step.get("status", "-"),
                "local_status": local_step.get("status", "-"),
                "public_ms": public_step.get("durationMs", 0),
                "local_ms": local_step.get("durationMs", 0),
                "public_output": public_step.get("outputSummary", ""),
                "local_output": local_step.get("outputSummary", ""),
                "tool_public": public_step.get("tool", ""),
                "tool_local": local_step.get("tool", ""),
            }
        )
    return rows


def safe_pct(value: float) -> str:
    return f"{value * 100:.1f}%"


def load_pdf_page_images(contract_path: Path) -> list[str]:
    previews: list[str] = []
    try:
        doc = fitz.open(contract_path)
    except Exception:
        return previews
    out_dir = DEFAULT_OUTPUT / "assets"
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    for index in range(min(3, doc.page_count)):
        page = doc.load_page(index)
        pix = page.get_pixmap(matrix=fitz.Matrix(1.2, 1.2), alpha=False)
        path = out_dir / f"{stamp}-page-{index + 1}.png"
        pix.save(path)
        previews.append(path.name)
    return previews


def render_html(
    contract_path: Path,
    public_run: ProfileRun,
    local_run: ProfileRun,
    output_path: Path,
) -> None:
    public_result = public_run.result_payload
    local_result = local_run.result_payload
    public_task = public_run.task_payload
    local_task = local_run.task_payload

    public_pages = public_result.get("pages") or []
    local_pages = local_result.get("pages") or []
    public_sections = public_result.get("sections") or []
    local_sections = local_result.get("sections") or []
    public_clauses = public_result.get("clauses") or []
    local_clauses = local_result.get("clauses") or []
    public_facts = public_result.get("keyFacts") or []
    local_facts = local_result.get("keyFacts") or []
    public_focuses = public_task.get("audit_focuses") or []
    local_focuses = local_task.get("audit_focuses") or []
    public_verification = public_task.get("verification_items") or []
    local_verification = local_task.get("verification_items") or []

    page_comp = build_page_comparison(public_pages, local_pages)
    section_comp = build_section_comparison(public_sections, local_sections)
    clause_comp = build_clause_comparison(public_clauses, local_clauses)
    fact_comp = build_key_fact_comparison(public_facts, local_facts)
    step_comp = build_step_comparison(public_task, local_task)

    page_similarity_avg = sum(item["similarity"] for item in page_comp) / max(len(page_comp), 1)
    total_public_chars = sum(item["public_chars"] for item in page_comp)
    total_local_chars = sum(item["local_chars"] for item in page_comp)
    total_missing_in_local = sum(item["local_missing_vs_public"] for item in page_comp)
    preview_assets = load_pdf_page_images(contract_path)
    manifest_path = output_path.with_suffix(".manifest.json")

    stage_cards = [
        {
            "name": "文档预处理与 OCR",
            "public": f"{len(public_pages)} 页 / {total_public_chars} 字 / {sum(len(p.get('blocks') or []) for p in public_pages)} blocks",
            "local": f"{len(local_pages)} 页 / {total_local_chars} 字 / {sum(len(p.get('blocks') or []) for p in local_pages)} blocks",
        },
        {
            "name": "章节还原",
            "public": f"{section_comp['public_count']} 个主条款 / {section_comp['public_child_count']} 个子项",
            "local": f"{section_comp['local_count']} 个主条款 / {section_comp['local_child_count']} 个子项",
        },
        {
            "name": "条款标签",
            "public": f"{len(public_clauses)} 条",
            "local": f"{len(local_clauses)} 条",
        },
        {
            "name": "关键字段",
            "public": f"{len(public_facts)} 项",
            "local": f"{len(local_facts)} 项",
        },
        {
            "name": "审计关注点",
            "public": f"{len(public_focuses)} 项",
            "local": f"{len(local_focuses)} 项",
        },
        {
            "name": "校验与证据链",
            "public": f"{len(public_verification)} 条",
            "local": f"{len(local_verification)} 条",
        },
    ]

    def esc(value: Any) -> str:
        return html.escape(str(value or ""))

    def json_block(value: Any) -> str:
        return esc(json.dumps(value, ensure_ascii=False, indent=2))

    top_summary_cards = [
        ("合同页数", max(len(public_pages), len(local_pages))),
        ("公网总耗时", f"{public_run.elapsed_ms / 1000:.1f}s"),
        ("内网总耗时", f"{local_run.elapsed_ms / 1000:.1f}s"),
        ("页面文本总字数", f"公网 {total_public_chars} / 内网 {total_local_chars}"),
        ("平均页相似度", safe_pct(page_similarity_avg)),
        ("相对未匹配字符", total_missing_in_local),
    ]

    html_content = f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>技术服务合同解析对比报告</title>
  <style>
    :root {{
      --bg: #08111f;
      --panel: #0f1d30;
      --panel-2: #13243a;
      --line: rgba(120, 180, 255, 0.18);
      --text: #edf4ff;
      --muted: #9cb5d7;
      --cyan: #5fdcff;
      --green: #41d39f;
      --amber: #ffb356;
      --red: #ff6a7d;
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      background:
        radial-gradient(circle at top left, rgba(57, 151, 255, 0.12), transparent 32%),
        linear-gradient(180deg, #07101c 0%, #091423 100%);
      color: var(--text);
      font-family: "Segoe UI", "PingFang SC", "Microsoft YaHei", sans-serif;
    }}
    .wrap {{ max-width: 1560px; margin: 0 auto; padding: 28px; }}
    .hero, .panel {{
      background: rgba(15, 29, 48, 0.92);
      border: 1px solid var(--line);
      border-radius: 24px;
      box-shadow: 0 24px 80px rgba(0, 0, 0, 0.26);
      backdrop-filter: blur(12px);
    }}
    .hero {{ padding: 28px; margin-bottom: 20px; }}
    .title {{ font-size: 34px; font-weight: 800; margin: 0 0 6px; }}
    .subtitle {{ color: var(--muted); margin: 0 0 16px; line-height: 1.7; }}
    .meta, .cards {{ display: grid; gap: 14px; }}
    .meta {{ grid-template-columns: repeat(auto-fit, minmax(260px, 1fr)); margin-bottom: 14px; }}
    .cards {{ grid-template-columns: repeat(auto-fit, minmax(180px, 1fr)); }}
    .chip, .card {{
      background: rgba(255,255,255,0.03);
      border: 1px solid rgba(255,255,255,0.06);
      border-radius: 18px;
      padding: 14px 16px;
    }}
    .chip .k, .card .k {{ color: var(--muted); font-size: 12px; letter-spacing: .08em; text-transform: uppercase; }}
    .chip .v, .card .v {{ margin-top: 8px; font-size: 18px; font-weight: 700; }}
    .grid {{ display: grid; grid-template-columns: 1.1fr .9fr; gap: 20px; margin-bottom: 20px; }}
    .panel {{ padding: 22px; }}
    h2 {{ margin: 0 0 14px; font-size: 22px; }}
    h3 {{ margin: 18px 0 10px; font-size: 16px; color: #d7e9ff; }}
    p, li {{ color: var(--muted); line-height: 1.7; }}
    table {{ width: 100%; border-collapse: collapse; margin-top: 10px; }}
    th, td {{ border-bottom: 1px solid rgba(255,255,255,0.08); padding: 10px 8px; vertical-align: top; text-align: left; font-size: 13px; }}
    th {{ color: #cfe4ff; font-weight: 700; }}
    td strong {{ color: var(--text); }}
    .ok {{ color: var(--green); }}
    .warn {{ color: var(--amber); }}
    .bad {{ color: var(--red); }}
    .twocol {{ display: grid; grid-template-columns: 1fr 1fr; gap: 16px; }}
    .code {{
      white-space: pre-wrap;
      word-break: break-word;
      background: rgba(0, 0, 0, 0.22);
      border: 1px solid rgba(255,255,255,0.06);
      border-radius: 16px;
      padding: 14px;
      font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
      font-size: 12px;
      color: #cde4ff;
      max-height: 320px;
      overflow: auto;
    }}
    .preview-list {{ display: flex; gap: 14px; flex-wrap: wrap; }}
    .preview-list img {{ width: 220px; border-radius: 16px; border: 1px solid rgba(255,255,255,0.08); }}
    .badge {{
      display: inline-flex; align-items: center; gap: 6px;
      padding: 5px 10px; border-radius: 999px; font-size: 12px;
      border: 1px solid rgba(255,255,255,0.08); background: rgba(255,255,255,0.04);
      color: #dfefff;
    }}
    .small {{ font-size: 12px; color: var(--muted); }}
    .section-list {{ max-height: 360px; overflow: auto; border: 1px solid rgba(255,255,255,0.06); border-radius: 16px; padding: 10px 12px; background: rgba(0,0,0,.12); }}
  </style>
</head>
<body>
  <div class="wrap">
    <div class="hero">
      <div class="badge">领导汇报版对比报告</div>
      <h1 class="title">技术服务合同解析性能对比</h1>
      <p class="subtitle">对同一份扫描版《15-20220929 技术服务合同》分别走公网链路与内网链路，逐节点对比页面文本量、章节还原、条款结构化、关键信息、审计关注点、校验链与执行耗时。OCR 主链路统一视为 Paddle 坐标基线，VL 只作为语义补充/增强能力单独观察；由于源 PDF 无文本层，文本差异仅用于辅助判断，不作为绝对漏识别结论。</p>
      <div class="meta">
        <div class="chip"><div class="k">测试文件</div><div class="v">{esc(contract_path.name)}</div></div>
        <div class="chip"><div class="k">生成时间</div><div class="v">{esc(datetime.now().strftime("%Y-%m-%d %H:%M:%S"))}</div></div>
        <div class="chip"><div class="k">报告路径</div><div class="v">{esc(str(output_path))}</div></div>
        <div class="chip"><div class="k">Run Manifest</div><div class="v">{esc(str(manifest_path))}</div></div>
      </div>
      <div class="cards">
        {"".join(f'<div class="card"><div class="k">{esc(k)}</div><div class="v">{esc(v)}</div></div>' for k, v in top_summary_cards)}
      </div>
    </div>

    <div class="grid">
      <div class="panel">
        <h2>一、模型链路概览</h2>
        <div class="twocol">
          <div>
            <h3>公网链路</h3>
            <ul>
              <li>档位：{esc(public_run.profile_label)} / {esc(public_run.profile_id)}</li>
              <li>文本模型：{esc((public_run.runtime_snapshot.get("profiles") or [{{}}])[0].get("textModel", ""))}</li>
              <li>OCR 主链路：Paddle 坐标基线；VL 语义补充：{esc("开启" if (public_run.runtime_snapshot.get("profiles") or [{{}}])[0].get("enableVlOcrEnhancement") else "关闭")}</li>
              <li>任务编号：{esc(public_run.task_id)}</li>
            </ul>
          </div>
          <div>
            <h3>内网链路</h3>
            <ul>
              <li>档位：{esc(local_run.profile_label)} / {esc(local_run.profile_id)}</li>
              <li>文本模型：{esc(next((p.get("textModel","") for p in local_run.runtime_snapshot.get("profiles", []) if p.get("id")==local_run.profile_id), ""))}</li>
              <li>OCR 主链路：Paddle 坐标基线；VL 语义补充：{esc("开启" if next((p.get("enableVlOcrEnhancement") for p in local_run.runtime_snapshot.get("profiles", []) if p.get("id")==local_run.profile_id), False) else "关闭")}</li>
              <li>任务编号：{esc(local_run.task_id)}</li>
            </ul>
          </div>
        </div>
        <p class="small">说明：本合同为扫描件，PDF 文本层为 0。报告不把 OCR 拆成公网/内网能力对比，而是把页面文本作为共同输入基线，再观察 VL 语义补充、文本模型理解和后续 Agent 节点的差异。</p>
        <p class="small">运行口径：Git {esc(git_commit())}；temperature=0；章节候选窗口=2页；内网并发=2；严格模型输出={esc(env_value("STRICT_MODEL_OUTPUTS"))}。</p>
      </div>
      <div class="panel">
        <h2>二、原件预览</h2>
        <div class="preview-list">
          {"".join(f'<img src="assets/{esc(name)}" alt="page preview" />' for name in preview_assets) if preview_assets else '<p>未生成预览图。</p>'}
        </div>
      </div>
    </div>

    <div class="panel" style="margin-bottom:20px;">
      <h2>三、阶段总览对比</h2>
      <table>
        <thead>
          <tr><th>阶段</th><th>公网链路</th><th>内网链路</th></tr>
        </thead>
        <tbody>
          {"".join(f"<tr><td><strong>{esc(item['name'])}</strong></td><td>{esc(item['public'])}</td><td>{esc(item['local'])}</td></tr>" for item in stage_cards)}
        </tbody>
      </table>
    </div>

    <div class="panel" style="margin-bottom:20px;">
      <h2>四、节点级执行对比</h2>
      <table>
        <thead>
          <tr>
            <th>节点</th>
            <th>公网状态 / 耗时</th>
            <th>内网状态 / 耗时</th>
            <th>公网输出摘要</th>
            <th>内网输出摘要</th>
          </tr>
        </thead>
        <tbody>
          {"".join(f"<tr><td><strong>{esc(row['name'])}</strong><div class='small'>{esc(row['tool_public'] or row['tool_local'])}</div></td><td>{esc(row['public_status'])} / {esc(row['public_ms'])}ms</td><td>{esc(row['local_status'])} / {esc(row['local_ms'])}ms</td><td>{esc(row['public_output'])}</td><td>{esc(row['local_output'])}</td></tr>" for row in step_comp)}
        </tbody>
      </table>
    </div>

    <div class="panel" style="margin-bottom:20px;">
      <h2>五、页面文本对齐与 VL 补充观察</h2>
      <table>
        <thead>
          <tr>
            <th>页码</th>
            <th>公网页面文本 / 块数</th>
            <th>内网页面文本 / 块数</th>
            <th>页相似度</th>
            <th>相对未匹配字符</th>
            <th>文本预览</th>
          </tr>
        </thead>
        <tbody>
          {"".join(f"<tr><td>第 {row['page']} 页</td><td>{row['public_chars']} / {row['public_blocks']}</td><td>{row['local_chars']} / {row['local_blocks']}</td><td class='{('bad' if row['similarity'] < 0.65 else 'warn' if row['similarity'] < 0.82 else 'ok')}'>{safe_pct(row['similarity'])}</td><td class='{('bad' if row['local_missing_vs_public'] > 60 else 'warn' if row['local_missing_vs_public'] > 20 else 'ok')}'>{row['local_missing_vs_public']}</td><td><div class='small'><strong>公网：</strong>{esc(row['public_preview'])}</div><div class='small' style='margin-top:6px;'><strong>内网：</strong>{esc(row['local_preview'])}</div></td></tr>" for row in page_comp)}
        </tbody>
      </table>
    </div>

    <div class="grid">
      <div class="panel">
        <h2>六、章节还原对比</h2>
        <div class="cards" style="grid-template-columns: repeat(4, minmax(0, 1fr)); margin-bottom: 14px;">
          <div class="card"><div class="k">公网主条款</div><div class="v">{section_comp['public_count']}</div></div>
          <div class="card"><div class="k">内网主条款</div><div class="v">{section_comp['local_count']}</div></div>
          <div class="card"><div class="k">公网子项</div><div class="v">{section_comp['public_child_count']}</div></div>
          <div class="card"><div class="k">内网子项</div><div class="v">{section_comp['local_child_count']}</div></div>
        </div>
        <div class="twocol">
          <div>
            <h3>公网识别顺序</h3>
            <div class="section-list">{"".join(f"<div>{index+1}. {esc(title)}</div>" for index, title in enumerate(section_comp['public_titles']))}</div>
          </div>
          <div>
            <h3>内网识别顺序</h3>
            <div class="section-list">{"".join(f"<div>{index+1}. {esc(title)}</div>" for index, title in enumerate(section_comp['local_titles']))}</div>
          </div>
        </div>
        <h3>内网相对缺失</h3>
        <ul>{"".join(f"<li>{esc(item)}</li>" for item in section_comp['missing_in_local']) or '<li>未观察到明显缺失。</li>'}</ul>
      </div>
      <div class="panel">
        <h2>七、条款与结构化字段对比</h2>
        <table>
          <thead><tr><th>核心标签</th><th>公网</th><th>内网</th><th>差值</th></tr></thead>
          <tbody>
            {"".join(f"<tr><td>{esc(row['label'])}</td><td>{row['public_count']}</td><td>{row['local_count']}</td><td class='{('bad' if row['delta'] < 0 else 'warn' if row['delta'] > 0 else 'ok')}'>{row['delta']}</td></tr>" for row in clause_comp['rows'])}
          </tbody>
        </table>
        <h3>关键字段一致性</h3>
        <table>
          <thead><tr><th>字段</th><th>公网</th><th>内网</th><th>结论</th></tr></thead>
          <tbody>
            {"".join(f"<tr><td>{esc(row['label'])}</td><td>{esc(row['public_value'])}</td><td>{esc(row['local_value'])}</td><td class='{('ok' if row['same'] else 'warn')}'>{'一致' if row['same'] else '存在差异'}</td></tr>" for row in fact_comp)}
          </tbody>
        </table>
      </div>
    </div>

    <div class="grid" style="margin-top:20px;">
      <div class="panel">
        <h2>八、审计关注点对比</h2>
        <div class="cards" style="grid-template-columns: repeat(4, minmax(0, 1fr)); margin-bottom: 14px;">
          <div class="card"><div class="k">公网关注点</div><div class="v">{len(public_focuses)}</div></div>
          <div class="card"><div class="k">内网关注点</div><div class="v">{len(local_focuses)}</div></div>
          <div class="card"><div class="k">公网来源分布</div><div class="v">{esc(summarize_audit_sources(public_focuses))}</div></div>
          <div class="card"><div class="k">内网来源分布</div><div class="v">{esc(summarize_audit_sources(local_focuses))}</div></div>
        </div>
        <div class="twocol">
          <div>
            <h3>公网前 5 项</h3>
            <ul>{"".join(f'<li><strong>{esc(item.get("title"))}</strong><br />{esc(item.get("reason"))}</li>' for item in public_focuses[:5])}</ul>
          </div>
          <div>
            <h3>内网前 5 项</h3>
            <ul>{"".join(f'<li><strong>{esc(item.get("title"))}</strong><br />{esc(item.get("reason"))}</li>' for item in local_focuses[:5])}</ul>
          </div>
        </div>
      </div>
      <div class="panel">
        <h2>九、校验链对比</h2>
        <div class="cards" style="grid-template-columns: repeat(2, minmax(0, 1fr)); margin-bottom: 14px;">
          <div class="card"><div class="k">公网状态分布</div><div class="v">{esc(summarize_verification(public_verification))}</div></div>
          <div class="card"><div class="k">内网状态分布</div><div class="v">{esc(summarize_verification(local_verification))}</div></div>
        </div>
        <table>
          <thead><tr><th>样例校验项</th><th>公网</th><th>内网</th></tr></thead>
          <tbody>
            {"".join(f"<tr><td>{esc((public_verification + local_verification)[index].get('name'))}</td><td>{esc(public_verification[index].get('status') if index < len(public_verification) else '-')}</td><td>{esc(local_verification[index].get('status') if index < len(local_verification) else '-')}</td></tr>" for index in range(min(max(len(public_verification), len(local_verification)), 8)))}
          </tbody>
        </table>
      </div>
    </div>

    <div class="panel" style="margin-top:20px;">
      <h2>十、汇报建议</h2>
      <ul>
        <li>如果领导重点关注“扫描件输入稳定性”，优先看第五部分的页面文本对齐表；这里反映共同 OCR 基线和 VL 语义增强后的输入差异。</li>
        <li>如果领导重点关注“结构理解能力”，优先看第六部分章节顺序与缺失章节。</li>
        <li>如果领导重点关注“后续规则引擎接入价值”，优先看第七部分关键字段一致性和第九部分校验链分布。</li>
        <li>建议汇报时把公网链路作为演示上限，把内网链路作为可私有化落地基线，强调两阶段章节重构已经把“看图”和“全局合并”拆开，后续可继续增强本地多模态候选识别能力。</li>
      </ul>
    </div>

    <div class="panel" style="margin-top:20px;">
      <h2>十一、原始数据摘录</h2>
      <div class="twocol">
        <div>
          <h3>公网任务快照</h3>
          <div class="code">{json_block({'task': public_result.get('task'), 'runtime': public_run.runtime_snapshot.get('currentProfileId'), 'task_id': public_run.task_id})}</div>
        </div>
        <div>
          <h3>内网任务快照</h3>
          <div class="code">{json_block({'task': local_result.get('task'), 'runtime': local_run.runtime_snapshot.get('currentProfileId'), 'task_id': local_run.task_id})}</div>
        </div>
      </div>
    </div>
  </div>
</body>
</html>"""

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(html_content, encoding="utf-8")
    manifest = {
        "generatedAt": datetime.now().isoformat(timespec="seconds"),
        "gitCommit": git_commit(),
        "contract": {
            "name": contract_path.name,
            "sha256": file_sha256(contract_path),
            "pages": max(len(public_pages), len(local_pages)),
        },
        "settings": {
            "strictModelOutputs": env_value("STRICT_MODEL_OUTPUTS"),
            "temperature": 0,
            "sectionBatchSize": 2,
            "internalParallelRequests": 2,
            "ocrBaseline": "Paddle coordinates; VL semantic enhancement is reported separately",
        },
        "runs": {
            "public": {
                "profileId": public_run.profile_id,
                "taskId": public_run.task_id,
                "model": (public_run.result_payload.get("task") or {}).get("modelName"),
                "elapsedMs": public_run.elapsed_ms,
                "sections": len(public_sections),
                "clauses": len(public_clauses),
                "keyFacts": len(public_facts),
                "auditFocuses": len(public_focuses),
                "verificationItems": len(public_verification),
                "runtimeSnapshot": public_run.runtime_snapshot,
            },
            "internal": {
                "profileId": local_run.profile_id,
                "taskId": local_run.task_id,
                "model": (local_run.result_payload.get("task") or {}).get("modelName"),
                "elapsedMs": local_run.elapsed_ms,
                "sections": len(local_sections),
                "clauses": len(local_clauses),
                "keyFacts": len(local_facts),
                "auditFocuses": len(local_focuses),
                "verificationItems": len(local_verification),
                "runtimeSnapshot": local_run.runtime_snapshot,
            },
        },
        "pageTextComparison": {
            "averageSimilarity": page_similarity_avg,
            "publicChars": total_public_chars,
            "internalChars": total_local_chars,
            "relativeUnmatchedChars": total_missing_in_local,
        },
    }
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="Run public/internal contract analysis and generate an HTML comparison report.")
    parser.add_argument("--api-base", default=DEFAULT_API_BASE)
    parser.add_argument("--contract", default=None, help="Path to the target contract PDF.")
    parser.add_argument("--public-profile", default="public")
    parser.add_argument("--local-profile", default="internal")
    parser.add_argument("--public-task-id", default=None, help="Reuse a completed persisted public task instead of running it.")
    parser.add_argument("--local-task-id", default=None, help="Reuse a completed persisted internal task instead of running it.")
    parser.add_argument("--timeout-seconds", type=int, default=2400)
    parser.add_argument("--output", default=None, help="Output HTML path.")
    args = parser.parse_args()

    contract_path = find_contract_path(args.contract)
    output_dir = DEFAULT_OUTPUT
    output_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    output_path = Path(args.output) if args.output else output_dir / f"technical-service-contract-compare-{stamp}.html"

    with httpx.Client(base_url=args.api_base, timeout=1200.0) as client:
        public_run = (
            load_profile_run_from_task(args.public_task_id, args.public_profile)
            if args.public_task_id
            else run_profile(client, contract_path, args.public_profile, args.timeout_seconds)
        )
        local_run = (
            load_profile_run_from_task(args.local_task_id, args.local_profile)
            if args.local_task_id
            else run_profile(client, contract_path, args.local_profile, args.timeout_seconds)
        )
        if not args.public_task_id or not args.local_task_id:
            switch_profile(client, args.public_profile)

    render_html(contract_path, public_run, local_run, output_path)
    print(output_path)


if __name__ == "__main__":
    main()
