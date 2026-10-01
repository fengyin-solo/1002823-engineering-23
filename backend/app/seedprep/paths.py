"""苗木基地数据准备的文件位置约定。

- data/seedling/        随仓库走：品种目录、按品种分文件的示例数据、准备好的数据
- var/logs/seedling/    本机留档：每次准备的核对日志（不随仓库走）
- var/seedling-store.json  本机运行期手工动作产生的变更（不随仓库走）
"""
from __future__ import annotations

from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[2]

DATA_DIR = BACKEND_ROOT / "data" / "seedling"
CATALOG_FILE = DATA_DIR / "catalog.json"
SAMPLES_DIR = DATA_DIR / "samples"
PREPARED_FILE = DATA_DIR / "prepared.json"
REPORT_FILE = DATA_DIR / "report.json"

VAR_DIR = BACKEND_ROOT / "var"
LOG_DIR = VAR_DIR / "logs" / "seedling"
WORKING_STORE_FILE = VAR_DIR / "seedling-store.json"
