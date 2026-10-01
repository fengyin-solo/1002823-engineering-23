"""准备好的苗木数据与运行期数据的读写。

prepared.json 随仓库走：另一处环境克隆下来不跑流程也能取到同一份数量；
working store 在本机 var/ 下：页面上手工登记 / 状态流转的变更不污染源数据。
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from app.seedprep.paths import PREPARED_FILE, WORKING_STORE_FILE


def _canonical_entry(row: dict[str, Any]) -> dict[str, Any]:
    """按固定字段顺序投影一条记录，供 canonical 序列化 / 签名使用。"""
    entry: dict[str, Any] = {}
    for field in [
        "id",
        "苗圃编号",
        "苗圃名称",
        "苗圃面积",
        "培育品种",
        "出圃周期",
        "培育数量",
        "出圃数量",
        "在圃数量",
        "管护人员",
        "status",
    ]:
        if field in row:
            entry[field] = row[field]
    return entry


def canonical_payload(entries: list[dict[str, Any]]) -> bytes:
    """确定性 JSON 序列化：字段与键排序固定，ensure_ascii=False，无多余空白。"""
    payload = [_canonical_entry(row) for row in entries]
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def load_prepared(path: Path | None = None) -> list[dict[str, Any]]:
    """读取准备好的数据；文件不存在或损坏时返回空，由流程重新生成。"""
    target = path or PREPARED_FILE
    if not target.exists():
        return []
    try:
        data = json.loads(target.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return []
    entries = data.get("entries", []) if isinstance(data, dict) else []
    return [dict(row) for row in entries if isinstance(row, dict)]


def save_prepared(
    entries: list[dict[str, Any]],
    signature: str,
    *,
    quantity_rule_source: str,
    path: Path | None = None,
) -> None:
    """覆盖写入 prepared.json；id 与编号顺序由调用方确定，写之前排序保证跨环境一致。"""
    target = path or PREPARED_FILE
    target.parent.mkdir(parents=True, exist_ok=True)
    ordered = sorted((_canonical_entry(row) for row in entries), key=lambda row: int(row.get("id", 0)))
    doc = {
        "source": "seedling-prepare-pipeline",
        "数量口径": quantity_rule_source,
        "signature": signature,
        "entries": ordered,
    }
    target.write_text(json.dumps(doc, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def load_working_store(path: Path | None = None) -> list[dict[str, Any]]:
    """读取本机运行期数据；不存在时返回空列表。"""
    target = path or WORKING_STORE_FILE
    if not target.exists():
        return []
    try:
        data = json.loads(target.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return []
    entries = data.get("entries", []) if isinstance(data, dict) else []
    return [dict(row) for row in entries if isinstance(row, dict)]


def save_working_store(entries: list[dict[str, Any]], path: Path | None = None) -> None:
    """持久化本机运行期数据（手工登记 / 状态流转后的最新状态）。"""
    target = path or WORKING_STORE_FILE
    target.parent.mkdir(parents=True, exist_ok=True)
    ordered = sorted((_canonical_entry(row) for row in entries), key=lambda row: int(row.get("id", 0)))
    doc = {"source": "seedling-working-store", "entries": ordered}
    target.write_text(json.dumps(doc, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
