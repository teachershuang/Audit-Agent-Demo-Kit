# 合同智能解析与审计关注点 Agent Demo

面向审计/风控场景的合同智能理解 Agent 原型。当前版本重点证明三件事：

1. 大模型或 mock Agent 可以理解合同结构与条款语义。
2. 所有解析结果都能回到合同原文证据，不做黑盒结论。
3. 审计输出是“关注方向 / 疑似风险 / 待核验事项”，并为后续接入规则引擎、知识图谱、企业关系库、RPA/API 预留扩展位。

界面采用 `enterprise AI cockpit` 风格：左侧合同审阅器，右侧审计智能面板，顶部任务栏，底部 Agent 状态带，适合演示与领导汇报场景。

## 项目结构

```text
frontend/   React + Vite + TypeScript + Tailwind + Zustand + Framer Motion
backend/    FastAPI + Pydantic + Agent orchestration + Mock/Qwen switch
docs/       API 文档与架构说明
samples/    示例合同摘要
```

## 启动方式

### 1. 启动后端

```bash
cd backend
python -m pip install -r requirements.txt
python -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

### 2. 启动前端

```bash
cd frontend
npm install
npm run dev
```

打开 [http://127.0.0.1:5173](http://127.0.0.1:5173)。

## 环境变量配置

将根目录 `.env.example` 复制为 `.env`，并按需配置：

```env
VITE_API_BASE_URL=http://127.0.0.1:8000
QWEN_API_KEY=
QWEN_BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1
QWEN_MODEL_NAME=qwen-plus
USE_MOCK_MODEL=true
```

说明：

1. `USE_MOCK_MODEL=true` 时，后端直接返回内置 mock 解析结果。
2. 当 `USE_MOCK_MODEL=false` 且已配置 `QWEN_API_KEY` 时，`QwenService` 会切到 OpenAI-compatible 接口。
3. 当前真实 Qwen 路径已做统一封装、JSON 修复和 schema 校验，但文档解析链路仍以 mock OCR/sample pages 为主。

## Mock 模式说明

当前内置一套完整 mock 数据，覆盖：

1. 合同页结构与文本块。
2. 章节树。
3. 条款标签。
4. 证据定位。
5. 审计关注方向。
6. 校验日志。
7. 关系配置。
8. Agent 过程日志。

即使不启动后端，前端也会在 API 不可用时自动回退到本地 mock 数据，以便快速演示。

## Qwen 接入方式

后端统一封装在 [backend/app/services/qwen_service.py](/E:/meeting_test/backend/app/services/qwen_service.py)：

```python
class QwenService:
    async def chat_json(self, system_prompt: str, user_prompt: str, schema: dict) -> dict:
        ...
```

能力说明：

1. 走 OpenAI-compatible `/chat/completions`。
2. 尝试修复 markdown code fence 和截断 JSON。
3. 使用 `jsonschema` 进行 schema 校验。
4. 调用失败时回退到 mock 结果。

## 前端页面说明

主页面为合同智能工作台，包含：

1. 顶部 Header：产品名、任务状态、模型名、总览置信度、上传/重解析/导出按钮。
2. 左侧合同原件区：页缩略图、缩放、滚动、证据高亮、左右联动。
3. 右侧 Tabs：
   - 章节还原
   - 条款标签
   - 关系配置
   - 审计关注点
   - 校验与证据链
   - Agent 过程日志
4. 底部状态带：任务编号、外部数据依赖、模型说明、当前限制。

## Agent 执行流程

```text
用户上传合同
  ↓
ContractAgent 创建任务与编排计划
  ↓
DocumentService 判断文档类型 / 预留 mineru、OCR、文本提取链路
  ↓
OCRService / MockOcrTool 提供页级文本块与坐标
  ↓
Planner 选择执行子任务
  ↓
AuditFocusAgent 基于条款与关系配置生成审计关注方向
  ↓
VerificationAgent 执行轻量异构校验
  ↓
EvidenceService 建立证据索引
  ↓
ConfidenceService 汇总工程化置信度
  ↓
返回前端工作台
```

## 数据结构说明

关键结构定义位于：

1. [backend/app/schemas/contract.py](/E:/meeting_test/backend/app/schemas/contract.py)
2. [backend/app/schemas/audit.py](/E:/meeting_test/backend/app/schemas/audit.py)
3. [backend/app/schemas/relation.py](/E:/meeting_test/backend/app/schemas/relation.py)
4. [backend/app/schemas/agent.py](/E:/meeting_test/backend/app/schemas/agent.py)

核心对象包括：

1. `ContractSection`
2. `ClauseTag`
3. `RelationConfig`
4. `AuditFocus`
5. `VerificationItem`
6. `AgentStep`

## 关系配置说明

“关系配置”不是死规则，而是未来规则引擎/图谱/主数据接入前的用户可配置分析上下文。当前支持：

1. 新增关系类型。
2. 编辑名称、说明、风险提示词。
3. 启用/停用。
4. 配置后续工具来源。
5. 配置优先级。
6. 变更后重新生成审计关注方向。

注意：涉及内部关联交易、供应商关系、账户异常的结论，当前必须表达为“疑似 / 待核验 / 需要外部数据确认”。

## API 文档

接口说明见：

1. [docs/api.md](/E:/meeting_test/docs/api.md)
2. [docs/architecture.md](/E:/meeting_test/docs/architecture.md)

## 后续扩展路线

1. `mineru` / PDF 智能拆解：区分文字件与扫描件，按链路切换文本提取或 OCR。
2. `rule_engine_adapter.py`：接入必备条款硬规则、付款控制规则、合同模板差异规则。
3. `knowledge_graph_adapter.py`：接入企业关系图谱与供应商路径查询。
4. `enterprise_relation_adapter.py`：接入工商数据、股东、法人、实控人。
5. `rpa_api_adapter.py`：接入付款系统、合同系统、发票系统、验收单据系统。
6. `evidence_service.py`：从 mock bbox 升级为真实 PDF block / OCR 坐标映射。

## 当前 Git 记录

已创建本地 Git 仓库，并完成阶段性提交：

1. `chore: initialize project scaffold`
2. `feat: build audit cockpit frontend prototype`
3. `feat: add fastapi agent orchestration backend`

当前未自动推送远端仓库，因为本地环境未提供现成的 Git 远端认证上下文。
