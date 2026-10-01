"""核对环节：示例数据去重与自洽校验。

核对口径全部来自 policy.py，本模块只负责“按口径找对不上的苗圃编号”：

1. 必填字段齐全、数量 / 周期字段是合法整数；
2. 出圃周期与品种目录一致（同品种必须同一周期）；
3. 出圃数量、培育数量非负，且出圃数量不超过培育数量；
4. 在圃数量必须等于 培育数量 - 出圃数量（以出圃数量为准）。

同一批示例里苗圃编号重复的，只认第一次出现的记录，后面的标记为 skipped，
既不参与核对，也不会在导入时叠成两份。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from app.seedprep.policy import (
    REQUIRED_SAMPLE_FIELDS,
    STATUS_ORDER,
    as_cycle,
    as_int,
    expected_in_nursery,
)


@dataclass
class Mismatch:
    code: str
    kind: str
    detail: str

    def as_dict(self) -> dict[str, str]:
        return {"苗圃编号": self.code, "对不上的项": self.kind, "说明": self.detail}


@dataclass
class ReconcileResult:
    valid_rows: list[dict[str, Any]] = field(default_factory=list)
    mismatches: list[Mismatch] = field(default_factory=list)
    skipped_duplicates: list[dict[str, str]] = field(default_factory=list)

    @property
    def passed(self) -> bool:
        return not self.mismatches


def _code_of(row: dict[str, Any], position: int) -> str:
    code = str(row.get("苗圃编号", "")).strip()
    return code or f"<第{position}条缺苗圃编号>"


def reconcile(
    rows: list[dict[str, Any]],
    catalog: dict[str, int],
    *,
    load_errors: list[str] | None = None,
) -> ReconcileResult:
    """对一批示例记录执行去重 + 自洽核对，返回通过、不通过与重复编号三类结果。"""
    result = ReconcileResult()
    seen_codes: set[str] = set()

    for message in load_errors or []:
        result.mismatches.append(Mismatch("<示例文件>", "文件读取", message))

    for position, row in enumerate(rows, start=1):
        code = _code_of(row, position)

        missing = [name for name in REQUIRED_SAMPLE_FIELDS if not str(row.get(name, "")).strip()]
        if missing:
            result.mismatches.append(Mismatch(code, "必填字段", f"缺少必填字段：{'、'.join(missing)}"))
            continue

        if code in seen_codes:
            # 同一批苗圃编号只认第一次：不叠两份，也不拿第二次再核一遍
            result.skipped_duplicates.append({
                "苗圃编号": code,
                "处理": "已跳过",
                "说明": "同一批示例中编号重复，只认第一次出现的记录",
            })
            continue
        seen_codes.add(code)

        row_mismatches: list[Mismatch] = []
        variety = str(row.get("培育品种", "")).strip()
        cycle = as_cycle(row.get("出圃周期"))
        raised = as_int(row.get("培育数量"))
        outplanted = as_int(row.get("出圃数量"))
        in_nursery = as_int(row.get("在圃数量"))

        if cycle is None:
            row_mismatches.append(Mismatch(code, "出圃周期", "出圃周期必须是正整数（天）"))
        elif variety not in catalog:
            row_mismatches.append(Mismatch(
                code, "培育品种", f"培育品种「{variety}」不在品种目录中，没有出圃周期标准"
            ))
        elif cycle != catalog[variety]:
            row_mismatches.append(Mismatch(
                code,
                "出圃周期",
                f"出圃周期 {cycle} 天与品种目录中「{variety}」的标准 {catalog[variety]} 天不一致",
            ))

        if raised is None:
            row_mismatches.append(Mismatch(code, "培育数量", "培育数量必须是整数"))
        elif raised < 0:
            row_mismatches.append(Mismatch(code, "培育数量", "培育数量不能为负数"))

        if outplanted is None:
            row_mismatches.append(Mismatch(code, "出圃数量", "出圃数量必须是整数"))
        elif outplanted < 0:
            row_mismatches.append(Mismatch(code, "出圃数量", "出圃数量不能为负数"))

        if in_nursery is None:
            row_mismatches.append(Mismatch(code, "在圃数量", "在圃数量必须是整数"))
        elif in_nursery < 0:
            row_mismatches.append(Mismatch(code, "在圃数量", "在圃数量不能为负数"))

        if raised is not None and outplanted is not None and outplanted > raised:
            row_mismatches.append(Mismatch(
                code,
                "数量关系",
                f"出圃数量 {outplanted} 超过培育数量 {raised}，总数对不上",
            ))

        if raised is not None and outplanted is not None and in_nursery is not None:
            expected = expected_in_nursery(raised, outplanted)
            if in_nursery != expected:
                row_mismatches.append(Mismatch(
                    code,
                    "在圃数量",
                    f"在圃数量登记为 {in_nursery}，按出圃数量核算应为 "
                    f"{raised} - {outplanted} = {expected}（以出圃数量为准）",
                ))

        if row_mismatches:
            result.mismatches.extend(row_mismatches)
        else:
            result.valid_rows.append(row)

    return result


def normalize_row(row: dict[str, Any], catalog: dict[str, int], entry_id: int) -> dict[str, Any]:
    """把通过核对的示例记录落成库里的标准结构。

    出圃周期取品种目录的标准值，在圃数量按出圃数量口径重算，
    保证写死的口径在入库数据上也只有这一份结果。
    """
    variety = str(row["培育品种"]).strip()
    raised = as_int(row.get("培育数量")) or 0
    outplanted = as_int(row.get("出圃数量")) or 0
    status = str(row.get("status", "")).strip()
    if status not in STATUS_ORDER:
        status = STATUS_ORDER[0]
    return {
        "id": entry_id,
        "苗圃编号": str(row["苗圃编号"]).strip(),
        "苗圃名称": str(row.get("苗圃名称", "")).strip(),
        "苗圃面积": row.get("苗圃面积", ""),
        "培育品种": variety,
        "出圃周期": catalog[variety],
        "培育数量": raised,
        "出圃数量": outplanted,
        "在圃数量": expected_in_nursery(raised, outplanted),
        "管护人员": str(row.get("管护人员", "")).strip(),
        "status": status,
        "pending": status != STATUS_ORDER[-1],
        "abnormal": status == "出圃中",
    }
