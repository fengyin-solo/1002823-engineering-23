#!/usr/bin/env bash
# 后端依赖引导：自检 -> 安装 -> 复验。
#
# 设计目标（对应"依赖没装好时要停在安装这一步并说明缺什么"）：
#   1. 先跑纯标准库的 check_env.py，缺依赖时明确打印缺哪个包、怎么装；
#   2. 已装齐则直接通过，绝不重复安装；
#   3. 没装齐时：优先用 .venv；建不了 venv / 没有 pip 时自动引导 pip 到本地目录，
#      再安装 requirements.txt；
#   4. 安装后必须复验，仍不齐就停在这一步（退出码 3），不会带着问题继续启动。
#
# 用法：./scripts/bootstrap.sh
#       source ./scripts/bootstrap.sh   # 本地目录安装时让 PYTHONPATH 在当前 shell 生效
set -uo pipefail

BACKEND_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
CHECK="$BACKEND_DIR/scripts/check_env.py"
VENV_DIR="$BACKEND_DIR/.venv"
LOCAL_LIBS="${PYTHON_TARGET:-$BACKEND_DIR/.pylibs}"

echo "==> [1/3] 依赖自检"
# 已存在 .venv 就用它自检（依赖装在 venv 里）；否则用系统 python3。
if [ -x "$VENV_DIR/bin/python" ]; then
  CHECK_PY=("$VENV_DIR/bin/python")
else
  CHECK_PY=(python3)
fi
set +e
"${CHECK_PY[@]}" "$CHECK"
rc=$?
set -e
if [ "$rc" -eq 0 ]; then
  echo "==> 依赖已齐全，跳过安装。"
  return 0 2>/dev/null || exit 0
elif [ "$rc" -ne 3 ]; then
  echo "==> 环境自检异常（退出码 $rc），已停止。" >&2
  exit "$rc"
fi

echo ""
echo "==> [2/3] 安装依赖（这一步装完会自动复验）"

PYTHON_CMD="python3"
USE_VENV=0

# 优先用项目内虚拟环境；建不了 venv（精简镜像缺 python3-venv）就退回本地目录安装。
if [ -x "$VENV_DIR/bin/python" ]; then
  USE_VENV=1
elif python3 -m venv "$VENV_DIR" >/dev/null 2>&1; then
  USE_VENV=1
  echo "    已创建虚拟环境：$VENV_DIR"
else
  echo "    无法创建 venv（系统可能缺 python3-venv），改为安装到本地目录：$LOCAL_LIBS"
  # 清掉建了一半的残缺 .venv（只有 python 软链、没有 pip），避免下次误判为可用。
  rm -rf "$VENV_DIR"
fi

bootstrap_getpip() {
  # $1 = 用来执行 get-pip 的解释器前缀（可能带 env PYTHONPATH=...）
  local py="$1"; shift
  local target="$1"; shift  # 空串=装进当前解释器环境；非空=--target 目录
  local tmp_getpip
  tmp_getpip="$(python3 -c 'import tempfile;print(tempfile.gettempdir())')/get-pip.py"
  echo "    正在用 get-pip.py 引导 pip……"
  curl -fsS https://bootstrap.pypa.io/get-pip.py -o "$tmp_getpip"
  if [ -n "$target" ]; then
    $py "$tmp_getpip" --target="$target"
  else
    $py "$tmp_getpip"
  fi
}

set +e
if [ "$USE_VENV" -eq 1 ]; then
  PYTHON_CMD="$VENV_DIR/bin/python"
  if ! "$PYTHON_CMD" -m pip --version >/dev/null 2>&1; then
    bootstrap_getpip "$PYTHON_CMD" ""
  fi
  echo "    $ $PYTHON_CMD -m pip install -r requirements.txt"
  "$PYTHON_CMD" -m pip install -r "$BACKEND_DIR/requirements.txt"
  install_rc=$?
else
  mkdir -p "$LOCAL_LIBS"
  if ! PYTHONPATH="$LOCAL_LIBS" python3 -m pip --version >/dev/null 2>&1; then
    bootstrap_getpip "python3" "$LOCAL_LIBS"
  fi
  echo "    $ PYTHONPATH=$LOCAL_LIBS python3 -m pip install --target=$LOCAL_LIBS -r requirements.txt"
  PYTHONPATH="$LOCAL_LIBS" python3 -m pip install --target="$LOCAL_LIBS" -r "$BACKEND_DIR/requirements.txt"
  install_rc=$?
fi
set -e

if [ "$install_rc" -ne 0 ]; then
  echo "" >&2
  echo "==> 依赖安装失败，已停在安装这一步。请检查网络或 pip 源后重试。" >&2
  exit 3
fi

echo ""
echo "==> [3/3] 安装后复验"
set +e
if [ "$USE_VENV" -eq 1 ]; then
  "$VENV_DIR/bin/python" "$CHECK"
else
  PYTHONPATH="$LOCAL_LIBS" python3 "$CHECK"
fi
verify_rc=$?
set -e

if [ "$verify_rc" -ne 0 ]; then
  echo "==> 复验仍未通过，依赖没装齐，停在安装这一步。" >&2
  exit 3
fi

if [ "$USE_VENV" -eq 1 ]; then
  echo "==> 完成。运行后端："
  echo "    $VENV_DIR/bin/python -m uvicorn app.main:app --host 127.0.0.1 --port 8000"
else
  export PYTHONPATH="$LOCAL_LIBS${PYTHONPATH:+:$PYTHONPATH}"
  echo "==> 完成。运行后端（已导出 PYTHONPATH）："
  echo "    python3 -m uvicorn app.main:app --host 127.0.0.1 --port 8000"
fi
return 0 2>/dev/null || exit 0
