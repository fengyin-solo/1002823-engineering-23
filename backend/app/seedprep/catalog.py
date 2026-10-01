"""品种目录与示例数据读取。

示例数据按培育品种分文件放在 samples/ 下，文件名即品种名；
出圃周期以品种目录 catalog.json 为唯一标准，示例文件里的周期只作为被核对对象。
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from app.seedprep.paths import CATALOG_FILE, SAMPLES_DIR


def _read_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def load_catalog(path: Path | None = None) -> dict[str, int]:
    """读取品种目录，返回 {培育品种: 出圃周期(天)}。"""
    raw = _read_json(path or CATALOG_FILE)
    entries = raw.get("品种目录", []) if isinstance(raw, dict) else []
    catalog: dict[str, int] = {}
    for entry in entries:
        name = str(entry.get("培育品种", "")).strip()
        cycle = entry.get("出圃周期")
        if name and isinstance(cycle, int) and cycle > 0:
            catalog[name] = cycle
    return catalog


def load_samples(samples_dir: Path | None = None) -> tuple[list[dict[str, Any]], list[str]]:
    """读取按品种分文件的示例数据。

    返回 (记录列表, 读取错误说明)；每个文件必须是记录数组，文件名即所属品种，
    记录自带的「培育品种」必须与文件名一致，防止放错文件。
    """
    directory = samples_dir or SAMPLES_DIR
    rows: list[dict[str, Any]] = []
    errors: list[str] = []

    if not directory.exists():
        return rows, [f"示例数据目录不存在：{directory}"]

    for path in sorted(directory.glob("*.json")):
        file_variety = path.stem
        try:
            data = _read_json(path)
        except json.JSONDecodeError as exc:
            errors.append(f"{file_variety}.json 不是合法 JSON：{exc.msg}（第 {exc.lineno} 行）")
            continue
        if not isinstance(data, list):
            errors.append(f"{file_variety}.json 内容必须是苗圃记录数组")
            continue
        for index, row in enumerate(data, start=1):
            if not isinstance(row, dict):
                errors.append(f"{file_variety}.json 第 {index} 条不是对象记录")
                continue
            row_variety = str(row.get("培育品种", "")).strip()
            if row_variety and row_variety != file_variety:
                errors.append(
                    f"{file_variety}.json 第 {index} 条培育品种为「{row_variety}」，"
                    f"与文件名「{file_variety}」不一致"
                )
            rows.append(row)

    return rows, errors
