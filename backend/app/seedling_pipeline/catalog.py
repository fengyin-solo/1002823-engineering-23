"""苗木品种口径（单一事实源）。

所有"出圃周期与在圃数量要自洽""出圃数量与在圃数量之间以谁为准"的口径都写死在这里，
数据准备、核对、接口、页面都只能读这里，不能各自再抄一份，避免换个地方口径就变了。
"""
from __future__ import annotations

from dataclasses import dataclass

# 出圃数量与在圃数量对不上时，以谁为准回推另一个。
# 业务约定：以【出圃数量】为准 —— 出圃是已经发生的事实，在圃是盘点推算值。
# 只允许在这里改，整套流程都引用这一个常量。
QUANTITY_AUTHORITY = "出圃数量"


@dataclass(frozen=True)
class Variety:
    """一个培育品种的标准培育口径。

    plants_per_batch：每个出圃批次的标准株数（同批次规模固定）。
    cycle_months：出圃周期（月）。一个周期内同时挂着这么多批在圃苗。
    """

    code: str
    name: str
    cycle_months: int
    plants_per_batch: int

    def in_nursery_baseline(self) -> int:
        """标准在圃基数 = 每批株数 × 周期内批次（=出圃周期月数）。

        这样"出圃周期"与"在圃数量"天然自洽：周期越长，地里同时在养的批次越多，
        在圃株数 = 每批株数 × 周期月数。
        """
        return self.plants_per_batch * self.cycle_months


# 示例数据允许出现的培育品种及其口径，按品种名索引。
VARIETIES: dict[str, Variety] = {
    v.name: v
    for v in [
        Variety("CHS", "香樟", cycle_months=12, plants_per_batch=200),
        Variety("OSM", "桂花", cycle_months=8, plants_per_batch=150),
        Variety("ZGM", "紫薇", cycle_months=6, plants_per_batch=120),
        Variety("HKM", "红花檵木", cycle_months=10, plants_per_batch=300),
        Variety("GML", "银杏", cycle_months=18, plants_per_batch=80),
    ]
}

# 出圃周期统一单位（示例数据里的 出圃周期 用整数月表达）。
CYCLE_UNIT = "月"


def get_variety(name: str) -> Variety | None:
    return VARIETIES.get(str(name or "").strip())
