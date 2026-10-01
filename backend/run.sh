#!/usr/bin/env bash
# 启动后端前先确认依赖装齐；没装齐就停在安装这一步并说明缺什么，不带病启动。
set -euo pipefail
cd "$(dirname "$0")"

# 选择解释器：优先项目 .venv，其次系统 python3。自检要用同一个解释器，
# 否则依赖明明装在 .venv 里，用系统 python 自检会误判为"缺失"。
if [ -x .venv/bin/python ]; then
  PY=.venv/bin/python
else
  PY=python3
fi

# 1) 依赖闸门：缺依赖时给出缺失清单与安装方式，退出码 3。
if ! "$PY" scripts/check_env.py; then
  echo "" >&2
  echo "run.sh：依赖未就绪（解释器：$PY），已停止启动。请先执行下面任一命令安装依赖后重试：" >&2
  echo "  ./scripts/bootstrap.sh" >&2
  echo "  python3 -m pip install -r requirements.txt" >&2
  exit 3
fi

# 2) 启动（依赖已在上面用同一解释器确认可用）。
exec "$PY" -m uvicorn app.main:app --host 127.0.0.1 --port 8000
