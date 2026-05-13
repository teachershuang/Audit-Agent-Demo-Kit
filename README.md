# 合同智能解析与审计关注点 Agent

面向审计与风控场景的合同智能理解工作台。系统支持上传合同 PDF 或图片，自动完成章节还原、条款标签识别、关键信息抽取、证据定位、审计关注事项生成、校验记录生成和左右联动审阅。

## 项目介绍

本项目的定位不是传统 OCR 工具，也不是固定规则系统，而是一个可扩展的 Agent 架构原型：

1. 用大模型理解合同结构与条款业务语义。
2. 所有输出必须可以回到原文证据。
3. 审计输出表达为关注事项、疑似风险、待核验事项。
4. 为后续规则引擎、知识图谱、企业关系数据、RPA/API 预留接入点。

## 技术栈

```text
frontend/   React + Vite + TypeScript + Tailwind + Zustand + Framer Motion
backend/    FastAPI + Pydantic + Qwen + PyMuPDF
docs/       API 文档与架构说明
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

将根目录 [.env.example](/E:/meeting_test/.env.example) 复制为 `.env`，按需填写：

```env
VITE_API_BASE_URL=http://127.0.0.1:8000
QWEN_API_KEY=
QWEN_BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1
QWEN_MODEL_NAME=qwen-plus
APP_NAME=合同智能解析与审计关注点 Agent
APP_ENV=development
```

说明：

1. `QWEN_API_KEY` 为空时，分析接口不会执行真实解析。
2. `QWEN_BASE_URL` 支持 OpenAI-compatible 接口。
3. 文字型 PDF 优先走 PDF 文本抽取，扫描件或图片走 Qwen-VL OCR。

## 示例合同说明

页面支持“快速载入”内置示例合同。这个入口会生成真实合同页图，并复用渲染阶段的文本坐标作为示例原文块；章节还原、条款标签、关键信息抽取、审计关注事项和校验记录仍然全部走真实 Agent 解析链路，不直接返回预制分析结果。

## Qwen 接入方式

统一封装位于 [backend/app/services/qwen_service.py](/E:/meeting_test/backend/app/services/qwen_service.py)：

```python
class QwenService:
    async def chat_json(self, system_prompt: str, user_prompt: str, schema: dict) -> dict:
        ...
```

能力说明：

1. 使用 `/chat/completions` 接口调用 Qwen。
2. 所有输出强制为 JSON。
3. 内置 JSON 修复。
4. 使用 `jsonschema` 做 schema 校验。
5. OCR 视觉链路使用 `qwen-vl-plus`。

## 前端页面说明

主页面是高密度企业审阅工作台：

1. 顶部任务栏：任务状态、模型名称、总览置信度、上传、重新解析、导出。
2. 左侧合同原件区：真实页图、缩放、滚动、证据高亮、点击联动。
3. 右侧分析区：章节还原、条款标签、关系配置、审计关注事项、校验与证据链、Agent 过程日志。
4. 底部状态带：任务编号、Agent 执行状态、模型服务、证据链状态。

## Agent 执行流程

```text
用户上传合同
  -> ContractAgent 创建任务
  -> DocumentService 判断文档类型
  -> OCRService 执行 PDF 文本抽取或 Qwen-VL OCR
  -> ContractParserAgent 还原章节结构
  -> ContractParserAgent 识别条款标签
  -> ContractParserAgent 抽取关键信息
  -> EvidenceService 建立证据回链
  -> AuditFocusAgent 生成审计关注事项
  -> VerificationAgent 输出校验记录
  -> ConfidenceService 汇总置信度
  -> 前端工作台展示
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
3. `KeyFact`
4. `RelationConfig`
5. `AuditFocus`
6. `VerificationItem`
7. `AgentStep`

## 关系配置说明

“关系配置”是用户可配置的分析上下文，不是死规则：

1. 可新增、编辑、启用、停用关系项。
2. 可配置风险提示词、工具来源、优先级。
3. 修改后可重新生成审计关注事项。
4. 涉及关联交易、供应商关系、账户异常等事项时，输出必须表达为疑似或待核验。

## 扫描件与证据定位说明

当前扫描件定位方式：

1. PDF 每页先渲染成页图。
2. 文字型 PDF 优先取原生文本块和坐标。
3. 低文本量页面或图片合同走 Qwen-VL OCR，返回归一化 `bbox`。
4. `EvidenceService` 再将章节、条款、关键信息锚定回 OCR 或 PDF block。

定位精度说明：

1. 文字型 PDF 的定位通常更稳定。
2. 扫描件的定位精度受清晰度、版式、倾斜、遮挡影响。
3. 当前更适合段落级和块级证据定位，不承诺词级精确框选。

## API 文档

1. [docs/api.md](/E:/meeting_test/docs/api.md)
2. [docs/architecture.md](/E:/meeting_test/docs/architecture.md)

## 后续扩展路线

1. 接入 MinerU 或更细粒度版面分析能力，增强复杂 PDF 拆解。
2. 接入规则引擎，补充必备条款、金额比例、付款约束等硬规则校验。
3. 接入知识图谱和企业关系数据，用于供应商、股东、法人、实控人关系核验。
4. 接入 RPA/API，对接合同、付款、发票、验收、审批等系统。

## Git 记录

当前已完成本地 Git 提交，包括项目初始化、前端工作台、后端 Agent 架构和真实解析链路接入。若需要推送到远端仓库，还需要本机提供 Git 远端认证上下文。
