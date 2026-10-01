"""准备台账（manifest）：核对通过后"已认下"的苗圃数据。

为什么需要它：
- 运行仓库是内存态，进程重启即空；而需求要求"重复导入同一批苗圃编号只认第一次"、
  "换台机器跑出来的数量是同一份"。
- 因此核对通过后把规范化条目确定性地落到本台账文件，之后每次启动/重跑都从台账装载：
  台账里已有的编号视为第一次已认下，再次出现一律跳过，绝不叠成两份。
- 台账内容由已入仓库的示例数据确定性生成（按编号排序），任何机器生成的内容逐字节一致。

文件是流水线运行产物（放在 logs 同级的 var 目录），不手工编辑；真正的数据源是
data/seedling_samples.json。
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from app.seedling_pipeline.importer import BUSINESS_COLUMNS
from app.seedling_pipeline.reconcile import KEY_CODE

VAR_DIR = Path(__file__).resolve().parent.parent.parent / "var" / "seedling_prepare"
MANIFEST_PATH = VAR_DIR / "manifest.json"


def load_manifest(path: Path | str | None = None) -> dict[str, Any] | None:
    p = Path(path) if path else MANIFEST_PATH
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None


def manifest_entries(path: Path | str | None = None) -> list[dict[str, Any]]:
    data = load_manifest(path)
    return list(data.get("entries", [])) if data else []


def save_manifest(entries: list[dict[str, Any]], *, checksum: str, meta: dict[str, Any],
                  path: Path | str | None = None) -> Path:
    """把核对通过的条目确定性落盘：按苗圃编号排序、固定列顺序。"""
    p = Path(path) if path else MANIFEST_PATH
    p.parent.mkdir(parents=True, exist_ok=True)
    ordered = sorted(entries, key=lambda e: str(e.get(KEY_CODE) or ""))
    clean = [{col: e.get(col) for col in BUSINESS_COLUMNS} for e in ordered]
    payload = {
        "data_version": meta.get("version"),
        "source": meta.get("source"),
        "checksum": checksum,
        "nurseries": len(clean),
        "entries": clean,
    }
    p.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return p


def reset_manifest(path: Path | str | None = None) -> None:
    """删除台账（主要给测试用）。"""
    p = Path(path) if path else MANIFEST_PATH
    if p.exists():
        p.unlink()
