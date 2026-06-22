# 快速启动

## 环境要求

- Python 3.11
- Node.js 20+
- npm 10+
- 可选：Redis
- 可选：内网 OCR 服务

## 1. 克隆仓库

```powershell
git clone https://github.com/teachershuang/Audit-Agent-Demo-Kit.git
cd Audit-Agent-Demo-Kit
```

## 2. 准备 Python 环境

```powershell
conda create -n contract_audit_base python=3.11 -y
conda activate contract_audit_base
pip install -r .\backend\requirements.txt
```

## 3. 安装前端依赖

```powershell
cd .\frontend
npm install
cd ..
```

## 4. 配置 `.env`

```powershell
Copy-Item .env.example .env
```

建议最少配置：

```env
QWEN_API_KEY=
QWEN_BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1
QWEN_MODEL_NAME=deepseek-v4-flash
QWEN_VISION_MODEL_NAME=qwen-vl-plus

LLM_API_KEY=
LLM_BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1
LLM_MODEL=deepseek-v4-flash
```

如需启用内网链路：

```env
INTERNAL_QWEN_API_KEY=
INTERNAL_QWEN_BASE_URL=http://your-internal-llm-host:4000/v1
INTERNAL_QWEN_MODEL_NAME=Qwen3.6-35B-A3B-GGUF

INTERNAL_PADDLE_SERVICE_MODE=remote_first
INTERNAL_PADDLE_REMOTE_BASE_URL=http://your-internal-ocr-host:8866
```

## 5. 启动服务

### 一键启动

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\start_all.ps1
```

### 分别启动

后端：

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\start_backend.ps1
```

前端：

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\start_frontend.ps1
```

## 6. 打开应用

- 前端：`http://127.0.0.1:5173`
- 后端：`http://127.0.0.1:8010`

## 7. 验证构建

```powershell
python -m compileall backend/app
cd frontend
npm run build
```

## 常见说明

- `frontend/node_modules` 与 `frontend/dist` 默认不提交。
- 运行日志会落到 `.\.run-logs\`。
- 上传文件会写入 `backend/uploads/`，该目录默认已忽略。
- 如果前端无法连接后端，优先检查 `VITE_API_BASE_URL` 与 `8010` 端口。
