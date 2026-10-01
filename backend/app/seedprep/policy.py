"""苗木基地数据准备的口径常量——全项目只在这里写死。

出圃数量与在圃数量冲突时以哪一侧为准，只有 QUANTITY_RULE_SOURCE 这一处定义；
核对、导入、页面展示全部通过 expected_in_nursery 取同一份口径，避免多处各写一套。
"""
from __future__ import annotations

from typing import Any

# 数量自洽口径：在圃数量 = 培育数量 - 出圃数量，出圃数量为准（只在此处写死）
QUANTITY_RULE_SOURCE = "出圃数量"
QUANTITY_RULE_TEXT = "在圃数量以「出圃数量」为准：在圃数量 = 培育数量 - 出圃数量"

# 出圃周期口径：同一培育品种的出圃周期以品种目录（catalog.json）为唯一标准
CYCLE_RULE_TEXT = "出圃周期以品种目录 catalog.json 为准，同品种各苗圃必须一致"

# 允许的苗圃状态；示例数据缺状态时取第一个
STATUS_ORDER = ["正常", "出圃中", "休整中", "已废弃"]

# 导入后落库的字段顺序，canonical 序列化也按它来，保证另一处环境算出同一份
RECORD_FIELDS = [
    "苗圃编号",
    "苗圃名称",
    "苗圃面积",
    "培育品种",
    "出圃周期",
    "培育数量",
    "出圃数量",
    "在圃数量",
    "管护人员",
]

REQUIRED_SAMPLE_FIELDS = [
    "苗圃编号",
    "苗圃名称",
    "培育品种",
    "培育数量",
    "出圃数量",
    "在圃数量",
]


def as_int(value: Any) -> int | None:
    """把数量字段转成 int；非数字（含 None、空串、'abc'）返回 None，交给核对环节报错。"""
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float) and value.is_integer():
        return int(value)
    if isinstance(value, str) and value.strip().lstrip("-").isdigit():
        return int(value.strip())
    return None


def as_cycle(value: Any) -> int | None:
    """出圃周期按天计，只接受正整数。"""
    number = as_int(value)
    return number if number is not None and number > 0 else None


def expected_in_nursery(raised: int, outplanted: int) -> int:
    """在圃数量的唯一计算口径：培育数量 - 出圃数量（以出圃数量为准）。"""
    return raised - outplanted
