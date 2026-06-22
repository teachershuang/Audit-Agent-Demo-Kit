# Contributing

欢迎通过 Issue、Discussion 和 Pull Request 参与改进。

## Suggested Workflow

1. Fork 仓库
2. 新建分支
3. 提交修改
4. 补充必要的截图、日志或复现步骤
5. 发起 Pull Request

## Development Notes

- 后端默认端口：`8010`
- 前端默认端口：`5173`
- 运行日志目录：`.run-logs/`
- 上传缓存目录：`backend/uploads/`

## Before Submitting

请至少执行：

```powershell
C:\Users\26423\.conda\envs\contract_audit_base\python.exe -m compileall backend/app
cd frontend
npm run build
```

## PR Expectations

- 说明改动目的
- 说明影响范围
- 如涉及 UI，请附带截图
- 如涉及模型链路或规则引擎，请附带调用日志或样例输入输出
