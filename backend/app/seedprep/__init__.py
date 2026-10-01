"""苗木基地数据准备流程。

同一条可重复流水线，三种入口共用：

- 命令行：python -m app.seedprep.cli
- 安装脚本：backend/prepare.sh（依赖缺失时停在安装步骤）
- 页面接口：POST /api/seedling/preparation/run

流程固定为：依赖检查 → 读取按培育品种分文件的示例数据 → 编号去重 →
出圃周期 / 数量自洽核对 → 首次导入 → 写数据文件与核对日志。
"""
from __future__ import annotations

from app.seedprep.dependencies import check_dependencies
from app.seedprep.pipeline import run_pipeline

__all__ = ["check_dependencies", "run_pipeline"]
