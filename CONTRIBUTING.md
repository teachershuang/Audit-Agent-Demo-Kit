# 贡献指南

欢迎通过 Issue、Discussion 和 Pull Request 参与改进。

## 推荐流程

1. Fork 仓库
2. 新建分支
3. 完成修改
4. 补充必要的截图、日志或复现步骤
5. 发起 Pull Request

## 开发约定

- 后端默认端口：`8010`
- 前端默认端口：`5173`
- 运行日志目录：`.run-logs/`
- 上传缓存目录：`backend/uploads/`

## 提交前检查

至少执行以下命令：

```powershell
python -m compileall backend/app
cd frontend
npm run build
```

## Pull Request 说明要求

- 说明改动目的
- 说明影响范围
- 如涉及 UI，请附带截图
- 如涉及模型链路或规则引擎，请附带调用日志或样例输入输出
