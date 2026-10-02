#!/usr/bin/env bash
set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$PROJECT_ROOT"

if [[ ! -f "backend/main.py" || ! -f "frontend/index.html" ]]; then
  echo "请从 CampusAI 项目目录运行此脚本。" >&2
  exit 1
fi

PYTHON="$PROJECT_ROOT/.venv/bin/python"
if [[ ! -x "$PYTHON" ]]; then
  echo "未找到 .venv/bin/python，请先创建虚拟环境并安装 requirements.txt。" >&2
  exit 1
fi

if ! "$PYTHON" -c "import fastapi, uvicorn" >/dev/null 2>&1; then
  echo "当前虚拟环境缺少 FastAPI 或 Uvicorn，请运行：.venv/bin/python -m pip install -r requirements.txt" >&2
  exit 1
fi

echo "CampusAI 正在启动：http://127.0.0.1:8000"
exec "$PYTHON" -m uvicorn backend.main:app --reload
