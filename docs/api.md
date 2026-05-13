# API 文档

Base URL: `http://127.0.0.1:8000`

## 合同任务

### `POST /api/contracts/upload`

上传合同文件并返回 `task_id`。

表单字段：

```text
file: UploadFile，可选
use_sample: bool，可选
```

返回：

```json
{
  "task_id": "task_xxxxxxxx"
}
```

### `GET /api/contracts/{task_id}`

获取任务元数据。

### `POST /api/contracts/{task_id}/analyze`

触发解析。当前会执行 mock/Agent 编排链路，并写入结果缓存。

### `GET /api/contracts/{task_id}/result`

获取核心合同解析结果。

返回主体：

1. `task`
2. `pages`
3. `sections`
4. `clauses`

### `GET /api/contracts/{task_id}/pages/{page}`

获取某页展示数据。当前返回页级 blocks 与 evidences，后续可替换成真实 PDF/page image 资源。

### `GET /api/contracts/{task_id}/evidence/{evidence_id}`

获取单条证据定位对象。

## 关系配置

### `GET /api/config/relations`

获取当前关系配置。

### `POST /api/config/relations`

新增关系配置。

### `PUT /api/config/relations/{relation_id}`

更新关系配置。

### `DELETE /api/config/relations/{relation_id}`

删除关系配置。

## 审计关注方向

### `POST /api/audit/generate`

基于 `task_id + relations` 重新生成审计关注方向。

请求：

```json
{
  "task_id": "task_xxxxxxxx",
  "relations": []
}
```

返回：

```json
{
  "auditFocuses": [],
  "verificationItems": [],
  "agentSteps": []
}
```

## 健康检查

### `GET /health`

返回当前服务状态与运行模式：

```json
{
  "status": "ok",
  "app": "Contract Audit Agent Demo",
  "mode": "mock"
}
```
