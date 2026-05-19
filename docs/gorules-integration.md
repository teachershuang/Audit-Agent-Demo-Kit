# GoRules 联调说明

## 推荐接入流程

1. 上传合同并完成 OCR、章节、条款、关键信息抽取。
2. 后端组装标准化 `rule_input`。
3. 将 `rule_input` 发送给 GoRules。
4. GoRules 返回命中规则结果。
5. 后端把规则结果并入 `VerificationAgent`，生成用户可读的校验说明。
6. 前端统一展示：
   - Agent 主动发现
   - 审计配置触发
   - 规则引擎命中

## 当前后端发给 GoRules 的主要输入

- `contract.contractNumber`
- `contract.sections`
- `contract.clauses`
- `contract.keyFacts`
- `entities.partyA`
- `entities.partyB`
- `entities.contractAmount`
- `entities.paymentTerms`
- `entities.acceptanceTerms`
- `entities.accountInfo`
- `derived.hasContractNumber`
- `derived.hasPaymentClause`
- `derived.hasAcceptanceClause`
- `derived.hasBreachClause`
- `derived.hasDisputeClause`
- `auditConfigs`

## 适合先联调的规则

### 1. 合同编号缺失

```text
when contract.contractNumber in [null, '', '未提取']
then hit("未成功提取合同编号，建议回看首页或签署页并人工复核。")
```

### 2. 付款条款缺少验收约束

```text
when derived.hasPaymentClause == true && derived.hasAcceptanceClause == false
then hit("识别到付款条款，但未识别到明确验收标准，存在先付款后验收风险。")
```

### 3. 违约责任条款缺失

```text
when derived.hasBreachClause == false
then hit("未识别到违约责任条款，建议审查合同责任约束是否完整。")
```

### 4. 账户信息缺失

```text
when entities.accountInfo in [null, '']
then hit("未抽取到账户信息，若合同涉及付款执行，建议补充收款账户核验。")
```

### 5. 有金额无付款安排

```text
when entities.contractAmount not in [null, ''] && derived.hasPaymentClause == false
then hit("已识别合同金额，但未识别到付款条件，建议核查付款安排是否缺失。")
```

## 联调建议

- 第一步只接 3 到 5 条确定性强的规则，不要一开始就接复杂的关联交易判断。
- GoRules 返回中间结构，不直接返回前端文案。
- 命中结果至少包含：
  - `ruleId`
  - `ruleName`
  - `severity`
  - `decision`
  - `reason`
  - `evidenceClauseIds`
  - `dependsOn`
- 大模型继续负责解释，规则引擎负责确定性命中。
