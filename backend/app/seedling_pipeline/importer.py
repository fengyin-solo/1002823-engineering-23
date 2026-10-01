"""示例数据读取与幂等导入。

- 示例数据文件按培育品种分组（data/seedling_samples.json 的 varieties 表），
  导入时拍平成有序列表，顺序完全确定。
- checksum 是这批数量的指纹：换一台机器、换一个目录，只要示例数据是同一份，
  算出来的指纹和总数量就完全相同。
- 导入按【苗圃编号】幂等：同一编号第二次导入只认第一次，不新增、不叠加成两份。
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from app.seedling_pipeline.reconcile import KEY_CODE, KEY_VARIETY

SAMPLE_PATH = Path(__file__).parent / "data" / "seedling_samples.json"

# 写入仓库时保留并统一这些业务列（顺序即展示顺序）。
BUSINESS_COLUMNS = [
    "苗圃编号", "苗圃名称", "苗圃面积", "培育品种",
    "出圃周期", "出圃数量", "在圃数量", "计划总量",
    "管护人员", "苗圃状态",
]


class SampleDataError(Exception):
    """示例数据文件缺失或结构不对时抛出，信息直接展示给操作者。"""


def load_sample(path: Path | str | None = None) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """读取按品种分组的示例数据，拍平成确定性有序的苗圃条目。

    返回 (entries, meta)；meta 里带 version、分组品种名、单位。
    """
    sample_path = Path(path) if path else SAMPLE_PATH
    if not sample_path.exists():
        raise SampleDataError(f"示例数据文件不存在：{sample_path}")
    try:
        payload = json.loads(sample_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise SampleDataError(f"示例数据不是合法 JSON：{sample_path}（{exc}）") from exc

    varieties = payload.get("varieties")
    if not isinstance(varieties, dict) or not varieties:
        raise SampleDataError("示例数据缺少非空的 varieties 分组")

    entries: list[dict[str, Any]] = []
    # 按品种名排序后再拍平，保证任何机器上顺序一致，不依赖 dict 插入顺序之类的偶然因素。
    for variety_name in sorted(varieties):
        group = varieties[variety_name]
        if not isinstance(group, list):
            raise SampleDataError(f"品种「{variety_name}」分组应为列表")
        for raw in group:
            if not isinstance(raw, dict):
                raise SampleDataError(f"品种「{variety_name}」分组内存在非对象记录")
            entry = {col: raw.get(col) for col in BUSINESS_COLUMNS}
            # 以分组键兜底培育品种，避免某条漏填时品种与所在分组不一致。
            if not entry.get(KEY_VARIETY):
                entry[KEY_VARIETY] = variety_name
            entries.append(entry)

    meta = {
        "version": payload.get("version", 1),
        "unit": payload.get("unit", "株"),
        "variety_count": len(varieties),
        "varieties": sorted(varieties),
        "source": str(sample_path.name),
    }
    return entries, meta


def quantity_fingerprint(entries: list[dict[str, Any]]) -> dict[str, Any]:
    """计算这批数量的确定性指纹与汇总，供跨环境比对"是不是同一份"。"""
    ordered = sorted(entries, key=lambda e: str(e.get(KEY_CODE) or ""))
    digest = hashlib.sha256()
    total_out = 0
    total_in = 0
    for e in ordered:
        out = int(e.get("出圃数量") or 0)
        in_n = int(e.get("在圃数量") or 0)
        total_out += out
        total_in += in_n
        # 只哈希会影响数量口径的列：编号、品种、周期、出圃、在圃、计划。
        line = "|".join(str(e.get(k, "")) for k in
                        ("苗圃编号", "培育品种", "出圃周期", "出圃数量", "在圃数量", "计划总量"))
        digest.update(line.encode("utf-8"))
        digest.update(b"\n")
    return {
        "checksum": digest.hexdigest(),
        "nurseries": len(ordered),
        "total_outplanted": total_out,
        "total_in_nursery": total_in,
        "total": total_out + total_in,
    }


def apply_to_store(entries: list[dict[str, Any]], rows: list[dict[str, Any]]) -> dict[str, int]:
    """把条目幂等写入内存仓库 rows。

    - 已存在同【苗圃编号】：保留第一次的内容，跳过（不更新、不叠加）。
    - 新编号：追加。id 取当前最大 id + 1，status/pending 等沿用仓库约定。

    返回计数：inserted 新增数、skipped 因重复跳过数。
    """
    existing = {str(row.get(KEY_CODE)): row for row in rows}
    next_id = max((int(row.get("id", 0)) for row in rows), default=0)
    inserted = 0
    skipped = 0

    for entry in entries:
        code = str(entry.get(KEY_CODE) or "").strip()
        if not code:
            continue  # 无编号的脏数据交给核对阶段报错，这里不入库
        if code in existing:
            # 重复导入同一批苗圃编号：只认第一次，绝不再插一份。
            skipped += 1
            continue
        next_id += 1
        row = {"id": next_id}
        row.update(entry)
        # 与仓库内其余模块字段对齐，便于状态流转与看板统计。
        row["status"] = entry.get("苗圃状态") or "正常"
        row["pending"] = row["status"] != "已废弃"
        row["abnormal"] = False
        rows.append(row)
        existing[code] = row
        inserted += 1

    return {"inserted": inserted, "skipped": skipped}
