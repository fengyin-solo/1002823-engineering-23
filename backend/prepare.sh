#!/usr/bin/env bash
# 苗木基地数据准备：在安装这一步确认依赖齐了，再跑「读取示例数据 → 核对 → 导入」流水线。
# 依赖缺失时停在安装步骤，打印缺什么、怎么装，不继续后面的核对与导入。
set -euo pipefail
cd "$(dirname "$0")"

PYTHON=".venv/bin/python"

if [ ! -x "$PYTHON" ]; then
  echo "==> 虚拟环境不存在，先创建（安装这一步）"
  python3 -m venv .venv || {
    echo "缺少 venv 组件。Debian/Ubuntu 请先执行：sudo apt install python3-venv"
    echo "然后重新运行 ./prepare.sh"
    exit 1
  }
fi

echo "==> 安装/核对依赖（requirements.txt）"
.venv/bin/pip install -q -r requirements.txt

echo "==> 依赖检查"
"$PYTHON" -m app.seedprep.cli --check

echo "==> 执行数据准备流水线"
"$PYTHON" -m app.seedprep.cli
