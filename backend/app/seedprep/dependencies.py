"""依赖检查：数据准备流程的第 1 步。

检查本身只用标准库，保证依赖没装好时也能跑出“缺什么”的结论。
检查项 = 运行 API 所需的第三方包 + Python 版本；缺失时给出可直接照做的安装命令，
调用方据此停在安装这一步，不继续后面的核对与导入。
"""
from __future__ import annotations

import importlib
import sys
from dataclasses import dataclass
from pathlib import Path

MIN_PYTHON = (3, 10)

# 包名 -> （import 名, 安装来源）；requirements.txt 是安装清单的唯一出处
THIRD_PARTY = [
    ("fastapi", "fastapi", "requirements.txt"),
    ("uvicorn", "uvicorn[standard]", "requirements.txt"),
    ("pydantic", "pydantic", "requirements.txt"),
]


@dataclass(frozen=True)
class MissingDependency:
    name: str
    reason: str
    install: str


def _pip_command() -> str:
    return ".venv/bin/pip install -r requirements.txt"


def check_dependencies(backend_root: Path | None = None) -> list[MissingDependency]:
    """返回缺失项列表；为空说明环境可以继续执行数据准备流程。"""
    missing: list[MissingDependency] = []

    if sys.version_info < MIN_PYTHON:
        missing.append(MissingDependency(
            name=f"Python>={MIN_PYTHON[0]}.{MIN_PYTHON[1]}",
            reason=f"当前 Python 为 {sys.version.split()[0]}，版本过低",
            install="安装 Python 3.10 或更高版本后重建虚拟环境：python3 -m venv .venv",
        ))

    for import_name, pip_name, source in THIRD_PARTY:
        try:
            module = importlib.import_module(import_name)
        except ImportError:
            missing.append(MissingDependency(
                name=pip_name,
                reason=f"无法导入模块 {import_name}，该依赖尚未安装",
                install=f"cd backend && {_pip_command()}",
            ))
            continue
        if import_name == "pydantic":
            version = getattr(module, "__version__", "0")
            try:
                major = int(version.split(".")[0])
            except (ValueError, IndexError):
                major = 1
            if major < 2:
                missing.append(MissingDependency(
                    name=pip_name,
                    reason=f"pydantic 版本为 {version}，接口模型要求 pydantic>=2.6",
                    install=f"cd backend && {_pip_command()}",
                ))

    requirements = (backend_root or Path(__file__).resolve().parents[2]) / "requirements.txt"
    if not requirements.exists():
        missing.append(MissingDependency(
            name="requirements.txt",
            reason="未找到依赖清单 requirements.txt",
            install="确认代码完整后重新克隆仓库，backend/requirements.txt 不应被删除",
        ))

    return missing


def render_missing(missing: list[MissingDependency]) -> str:
    """把缺失项渲染成要给人看的说明（CLI 输出 / 页面提示共用）。"""
    lines = ["依赖检查未通过，已停在安装这一步，未执行核对与导入。", f"缺失 {len(missing)} 项："]
    for item in missing:
        lines.append(f"- {item.name}：{item.reason}")
        lines.append(f"  安装方式：{item.install}")
    return "\n".join(lines)
