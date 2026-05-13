# 架构说明

## 定位

该项目不是完整审计系统，也不是 OCR 工具集合，而是“合同智能解析与审计关注点 Agent 原型”。

设计重点：

1. 模型输出必须附带证据。
2. 审计关注点不是死规则结论。
3. 内部关联交易等高敏感判断必须标记为待核验。
4. 后端必须保留规则引擎、知识图谱、企业关系数据和 RPA/API 的接入位。

## 后端分层

### `agents/`

1. `contract_agent.py`
   负责任务编排。
2. `audit_focus_agent.py`
   基于合同内容和关系配置生成关注方向。
3. `verification_agent.py`
   执行轻量异构校验。
4. `planner.py`
   根据文件类型规划执行链。

### `services/`

1. `document_service.py`
   判断文件类型、预留 mineru/文本提取/OCR 分流逻辑。
2. `ocr_service.py`
   当前走 mock OCR，后续可接 PaddleOCR、Qwen-VL 等。
3. `qwen_service.py`
   统一模型调用、JSON 修复和 schema 校验。
4. `evidence_service.py`
   建立结果到原文坐标的映射索引。
5. `confidence_service.py`
   汇总工程化置信度。
6. `relation_config_service.py`
   管理关系配置项。

### `tools/`

1. `mock_ocr_tool.py`
2. `qwen_llm_tool.py`
3. `rule_engine_adapter.py`
4. `knowledge_graph_adapter.py`
5. `enterprise_relation_adapter.py`
6. `rpa_api_adapter.py`

这些 adapter 当前返回 mock，占位但不写死真实审计结论。

### `storage/`

`local_store.py` 使用内存 + 本地文件元数据保存任务状态，适合 demo。后续可以替换为 Redis / PostgreSQL / 对象存储。

## 前端分层

### 左侧

`ContractViewer` 实现合同原件审阅、页缩略图、缩放与证据高亮。

### 右侧

`AnalysisTabs` 承载 6 个核心模块：

1. 章节还原
2. 条款标签
3. 关系配置
4. 审计关注点
5. 校验与证据链
6. Agent 过程日志

### 状态管理

`Zustand` 维护：

1. 当前任务结果
2. 当前激活 tab
3. 当前激活证据
4. 当前页码
5. 关系配置
6. 审计关注点与校验结果

## 未来扩展点

### 1. MinerU / PDF 智能文档链路

建议增加：

1. 文本型 PDF：优先 `mineru` / PDF 文本抽取。
2. 扫描件：先版面分析，再 OCR。
3. 混合文档：页级路由。

### 2. 规则引擎

适合接入：

1. 必备条款检查。
2. 付款节点与验收节点匹配规则。
3. 合同模板偏差规则。
4. 金额比例阈值规则。

### 3. 知识图谱 / 企业关系库

适合接入：

1. 供应商股东 / 法人 / 实控人路径。
2. 集团内部关联交易路径。
3. 重复供应商和异常关系聚类。

### 4. RPA / API

适合接入：

1. 付款系统。
2. 发票系统。
3. 合同归档系统。
4. 验收单据系统。
5. 审批流系统。

## 风险表述约束

所有高敏感结果必须避免绝对化表述：

1. 不使用“已确认违规”“确定存在关联交易”“审计结论”。
2. 统一采用“疑似风险”“待核验事项”“建议人工复核”“需外部数据确认”。
