# API Overview

Base URL:

```text
http://127.0.0.1:8010
```

## Health & Runtime

### `GET /health`

检查服务状态、当前模型档位和模型探针结果。

### `GET /api/runtime/model-profiles`

获取可用的运行时模型档位。

### `POST /api/runtime/model-profiles/switch`

切换当前运行时档位。

Request:

```json
{
  "profile_id": "public"
}
```

## Contract Analysis

### `POST /api/contracts/upload`

上传合同文件。

Form fields:

- `file`
- `use_builtin_example`

### `POST /api/contracts/{task_id}/analyze`

启动合同分析任务。

### `GET /api/contracts/{task_id}`

获取任务进度、当前阶段、耗时与知识底座校验状态。

### `GET /api/contracts/{task_id}/result`

获取完整解析结果。

### `GET /api/contracts/{task_id}/pages/{page}`

获取页面结构数据。

### `GET /api/contracts/{task_id}/pages/{page}/image`

获取页面图片。

### `GET /api/contracts/{task_id}/evidence/{evidence_id}`

获取指定证据对象。

### `POST /api/contracts/{task_id}/reanalyze-from-result`

基于已编辑结果重新生成审计关注点和校验结果。

## Audit Config

### `GET /api/config/relations`

获取审计配置列表。

### `POST /api/config/relations`

新增审计配置。

### `PUT /api/config/relations/{relation_id}`

修改审计配置。

### `DELETE /api/config/relations/{relation_id}`

删除审计配置。

## Audit Focus

### `POST /api/audit/generate`

根据合同解析结果和配置重新生成审计关注点。

## Rule Engine

### `GET /api/rules/runtime`

查看规则引擎运行时状态。

### `POST /api/rules/evaluate`

执行规则校验。

## Knowledge Base

### `POST /api/base/documents/upload`

上传制度 / 范本文档。

### `GET /api/base/documents`

列出制度文档。

### `GET /api/base/documents/{doc_id}/metadata`

获取制度文档元信息。

### `GET /api/base/documents/{doc_id}/clauses`

获取文档条款。

### `GET /api/base/rules`

列出规则。

### `GET /api/base/rules/{rule_id}/metadata`

查看规则及来源条款。

### `POST /api/base/contracts/review/start`

异步发起合同制度审查任务。

### `GET /api/base/contracts/review-tasks/{task_id}`

轮询制度审查任务状态。

### `GET /api/base/contracts/{contract_id}/schema`

查看结构化字段。

### `GET /api/base/contracts/{contract_id}/report`

查看制度审查报告。

## Logs

### `POST /api/logs/frontend`

写入前端事件日志。

### `GET /api/logs/file?path=...`

读取指定日志文件内容。
