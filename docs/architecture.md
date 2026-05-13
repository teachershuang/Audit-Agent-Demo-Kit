# 架构说明

## 定位

这是一个面向审计与风控场景的合同智能理解 Agent 工作台，不是简单 OCR 工具，也不是固定规则系统。

设计原则：

1. 所有模型输出必须带证据。
2. 审计输出是关注事项，不是最终审计结论。
3. 涉及关联交易、账户异常、供应商关系等高敏感事项时，必须表达为待核验。
4. 架构必须预留规则引擎、知识图谱、企业关系数据和业务系统对接能力。

## 后端分层

### `agents/`

1. `contract_agent.py`
   负责任务编排。
2. `contract_parser_agent.py`
   负责章节还原、条款标签识别、关键信息抽取。
3. `audit_focus_agent.py`
   负责生成审计关注事项。
4. `verification_agent.py`
   负责生成校验记录。
5. `planner.py`
   根据文档类型选择执行链路。

### `services/`

1. `document_service.py`
   判断文档类型并规划解析链路。
2. `ocr_service.py`
   执行 PDF 文本抽取、页图渲染和 Qwen-VL OCR。
3. `qwen_service.py`
   统一管理 Qwen 文本与视觉模型调用、JSON 修复与 schema 校验。
4. `evidence_service.py`
   将模型输出锚定回原文块坐标。
5. `confidence_service.py`
   汇总章节、条款和关注事项的工程化置信度。
6. `relation_config_service.py`
   管理关系配置项。

### `tools/`

1. `qwen_llm_tool.py`
2. `rule_engine_adapter.py`
3. `knowledge_graph_adapter.py`
4. `enterprise_relation_adapter.py`
5. `rpa_api_adapter.py`

这些 adapter 当前作为接入位保留，用于后续挂接外部系统，不在当前版本中写死业务结论。

### `storage/`

`local_store.py` 当前使用内存和本地文件元数据保存任务状态，适合本地演示和联调。后续可切换为 Redis、PostgreSQL 或对象存储。

## 解析链路

```text
上传合同
  -> 判断文件类型
  -> PDF 文本抽取 / 页图渲染 / 图片 OCR
  -> 章节还原
  -> 条款标签识别
  -> 关键信息抽取
  -> 证据回链
  -> 审计关注事项生成
  -> 校验记录生成
  -> 置信度汇总
```

## 扫描件处理策略

当前扫描件链路：

1. 先将 PDF 按页渲染成图像。
2. 检查原生文本块质量。
3. 对文本量不足的页面调用 `qwen-vl-plus` OCR。
4. 统一转换为 `DocumentBlock`。
5. 再由 `EvidenceService` 做证据锚定。

这意味着扫描件可以做真实证据定位，但精度依赖 OCR 质量，通常更适合块级或段级高亮。

## 前端架构

### 左侧合同原件区

`ContractViewer` 显示真实页图、证据高亮、页码切换和联动定位。

### 右侧分析区

`AnalysisTabs` 承载 6 个核心模块：

1. 章节还原
2. 条款标签
3. 关系配置
4. 审计关注事项
5. 校验与证据链
6. Agent 过程日志

### 状态管理

`Zustand` 统一管理：

1. 当前任务结果
2. 当前激活标签页
3. 当前激活证据
4. 当前页码
5. 关系配置
6. 审计关注事项与校验结果

## 扩展点

1. MinerU 或版面分析模型，用于复杂 PDF 结构解析。
2. 规则引擎，用于付款约束、必备条款、模板偏差等硬规则。
3. 知识图谱与企业关系库，用于主体、股东、法人、实控人路径核验。
4. RPA/API，用于合同、付款、发票、验收、审批系统联查。

## 风险表述约束

系统对高敏感事项统一采用以下表达：

1. 疑似风险
2. 待核验事项
3. 建议人工复核
4. 需要外部数据确认

禁止使用“已确认违规”“确定存在关联交易”“审计结论”等绝对化措辞。
