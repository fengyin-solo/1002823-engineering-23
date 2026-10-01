"""苗木基地数据准备流水线。

把"手工往本地库里录"换成一段可重复执行的准备流程：

    示例数据(按品种分组 JSON) -> 规范化导入(同编号幂等) -> 自动核对 -> 就绪闸门

- 示例数据：app/seedling_pipeline/data/seedling_samples.json，按培育品种分好，
  任何机器跑出来的数量都一致，指纹(checksum)也一致。
- 核对规则、品种口径、"以出圃数量为准"都集中在本包内，路由层不做业务判断。
- 核对不通过时数据不会被标记为"已就绪"，并把对不上的苗圃编号写进留档日志。

只用标准库实现，保证数据准备这一步本身不引入额外依赖；FastAPI 等服务依赖
由 scripts/bootstrap.sh 单独负责检查与安装。
"""
from __future__ import annotations

from app.seedling_pipeline.catalog import VARIETIES, QUANTITY_AUTHORITY
from app.seedling_pipeline.pipeline import (
    PipelineResult,
    prepare_seedlings,
    current_status,
    last_report,
)

__all__ = [
    "VARIETIES",
    "QUANTITY_AUTHORITY",
    "PipelineResult",
    "prepare_seedlings",
    "current_status",
    "last_report",
]
