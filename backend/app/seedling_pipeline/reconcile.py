"""核对规则：导入后自动跑一遍，把对不上的苗圃编号挑出来。

核对口径全部来自 catalog，本文件不重复定义品种参数。三类核对：

1. 出圃周期自洽：出圃周期必须等于该品种 catalog 里登记的标准周期。
2. 在圃数量自洽：在圃数量必须等于「每批株数 × 出圃周期月数」的标准基数。
3. 数量守恒：出圃数量 + 在圃数量 = 计划总量；对不上时以【出圃数量】为准，
   回推出正确的在圃数量，并在 issue 里给出期望值（不静默改数，先报出来）。

任意一条不通过，整批数据都不算"已就绪"。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from app.seedling_pipeline.catalog import QUANTITY_AUTHORITY, get_variety

# 编号 / 品种 / 三个数量字段是核对与导入的必备列。
KEY_CODE = "苗圃编号"
KEY_VARIETY = "培育品种"
KEY_CYCLE = "出圃周期"
KEY_OUT = "出圃数量"
KEY_IN = "在圃数量"
KEY_PLAN = "计划总量"

REQUIRED_COLUMNS = [KEY_CODE, KEY_VARIETY, KEY_CYCLE, KEY_OUT, KEY_IN, KEY_PLAN]


@dataclass
class Issue:
    code: str           # 出问题的苗圃编号（取不到编号时给 <未命名>）
    rule: str           # 命中的核对规则
    message: str        # 可读说明
    expected: Any = None  # 期望值（便于按出圃数量回推修正）
    actual: Any = None    # 实际值


@dataclass
class ReconcileReport:
    ok: bool
    checked: int
    issues: list[Issue] = field(default_factory=list)

    @property
    def mismatch_codes(self) -> list[str]:
        """对不上的苗圃编号（去重、保序）。"""
        seen: set[str] = set()
        codes: list[str] = []
        for issue in self.issues:
            if issue.code not in seen:
                seen.add(issue.code)
                codes.append(issue.code)
        return codes

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "checked": self.checked,
            "mismatch_codes": self.mismatch_codes,
            "authority": QUANTITY_AUTHORITY,
            "issues": [
                {
                    "苗圃编号": i.code,
                    "rule": i.rule,
                    "message": i.message,
                    "expected": i.expected,
                    "actual": i.actual,
                }
                for i in self.issues
            ],
        }


def _to_int(value: Any) -> int | None:
    """宽容地把 '12' / 12 / 12.0 解析成整数；无法解析返回 None。"""
    if isinstance(value, bool):  # bool 是 int 的子类，先排除
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float) and value.is_integer():
        return int(value)
    text = str(value or "").strip()
    if text.isdigit():
        return int(text)
    return None


def reconcile(entries: list[dict[str, Any]]) -> ReconcileReport:
    """对规范化后的苗圃条目逐条核对。"""
    issues: list[Issue] = []
    seen_codes: set[str] = set()

    for entry in entries:
        code = str(entry.get(KEY_CODE) or "").strip() or "<未命名>"
        variety_name = str(entry.get(KEY_VARIETY) or "").strip()

        # 编号重复在导入阶段已幂等处理，这里仍单独报，方便核对原始批次。
        if code in seen_codes:
            issues.append(Issue(code, "编号重复", f"苗圃编号 {code} 在同一批里出现多次，重复导入只认第一次"))
        seen_codes.add(code)

        missing = [col for col in REQUIRED_COLUMNS if str(entry.get(col) or "").strip() == ""]
        if missing:
            issues.append(Issue(code, "缺字段", f"缺少必填字段：{'、'.join(missing)}"))
            continue  # 缺字段后无法做数量核对，跳过本条目后续规则

        variety = get_variety(variety_name)
        if variety is None:
            issues.append(Issue(
                code, "品种未登记",
                f"培育品种「{variety_name}」不在品种口径表里，无法判定周期与在圃基数",
            ))
            continue

        cycle = _to_int(entry.get(KEY_CYCLE))
        out = _to_int(entry.get(KEY_OUT))
        in_nursery = _to_int(entry.get(KEY_IN))
        plan = _to_int(entry.get(KEY_PLAN))

        # 规则 1：出圃周期自洽
        if cycle != variety.cycle_months:
            issues.append(Issue(
                code, "出圃周期不符",
                f"{variety_name} 的标准出圃周期应为 {variety.cycle_months} 个月，实际 {cycle}",
                expected=variety.cycle_months, actual=cycle,
            ))

        # 在圃基数（出圃周期与在圃数量自洽的基准）
        expected_baseline = variety.in_nursery_baseline()

        # 数量字段必须是非负整数，否则后面的比较没有意义
        for label, val in (("出圃数量", out), ("在圃数量", in_nursery), ("计划总量", plan)):
            if val is None or val < 0:
                issues.append(Issue(code, "数量非法", f"{label} 必须是非负整数，实际为 {entry.get(label)!r}"))
        if out is None or in_nursery is None or plan is None or min(out, in_nursery, plan) < 0:
            continue

        # 规则 2：在圃数量自洽（= 每批株数 × 周期月数）
        if in_nursery != expected_baseline:
            issues.append(Issue(
                code, "在圃数量不自洽",
                f"在圃数量应为 每批{variety.plants_per_batch}株 × 周期{variety.cycle_months}月 "
                f"= {expected_baseline}，实际 {in_nursery}",
                expected=expected_baseline, actual=in_nursery,
            ))

        # 规则 3：数量守恒。对不上时以【出圃数量】为准回推在圃数量
        expected_plan = out + expected_baseline
        if plan != out + in_nursery or in_nursery != expected_baseline:
            issues.append(Issue(
                code, "数量不守恒",
                f"出圃数量({out}) + 在圃数量({in_nursery}) 与计划总量({plan}) 对不上；"
                f"以【{QUANTITY_AUTHORITY}】为准，在圃数量应为 {expected_baseline}，"
                f"计划总量应为 {expected_plan}",
                expected={"在圃数量": expected_baseline, "计划总量": expected_plan},
                actual={"在圃数量": in_nursery, "计划总量": plan},
            ))

    return ReconcileReport(ok=not issues, checked=len(entries), issues=issues)
