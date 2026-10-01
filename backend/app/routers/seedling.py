"""苗木基地接口：维护苗圃，覆盖登记出圃、休整轮作、废弃苗圃等动作。"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query

from app.schemas import ActionResult, EntryPayload, PageResult
from app.services.seedling import SeedlingService

router = APIRouter(prefix="/api/seedling", tags=["苗木基地"])

service = SeedlingService()

LIST_FIELDS = [
    "苗圃编号", "苗圃名称", "苗圃面积", "培育品种", "出圃周期",
    "培育数量", "出圃数量", "在圃数量", "管护人员", "苗圃状态",
]
STATUSES = ["正常", "出圃中", "休整中", "已废弃"]


# ---- 数据准备流程（静态路径必须放在 /{entry_id} 之前，否则会被当成编号）----

@router.get("/preparation")
def preparation_status() -> dict[str, Any]:
    """数据准备状态：是否已核对通过、数量汇总、对不上的编号、日志留档位置。"""
    return service.prepare_status()


@router.post("/preparation/run")
def preparation_run() -> dict[str, Any]:
    """重新跑一遍「依赖检查 → 示例数据 → 核对 → 首次导入」的可重复流程。

    依赖没装好时停在安装这一步，HTTP 503 并说明缺什么；
    核对不通过时报告 ready=false 并列明对不上的苗圃编号，不算准备好。
    """
    report, missing = service.run_prepare()
    if missing:
        raise HTTPException(status_code=503, detail={
            "stopped": "install",
            "message": service.explain_missing(missing),
            "missing": [item.name for item in missing],
        })
    return report


@router.get("/preparation/log")
def preparation_log() -> dict[str, Any]:
    """最近一次核对日志原文：每次导入都留档，页面可直接查看原因。"""
    return service.latest_log()


@router.get("/export")
def export_entries() -> dict[str, Any]:
    """导出苗木基地清单：返回当前过滤条件下的全量数据。"""
    items, total = service.list_entries(page=1, size=10000)
    return {"module": "seedling", "total": total, "items": items}


# ---- 苗圃台账 ----

@router.get("", response_model=PageResult[dict])
def list_entries(
    keyword: str | None = Query(default=None, description="按苗圃编号检索"),
    variety: str | None = Query(default=None, description="按培育品种检索"),
    status: str | None = Query(default=None, description="正常、出圃中、休整中、已废弃"),
    page: int = 1,
    size: int = 20,
) -> PageResult[dict]:
    """按苗圃编号、培育品种与状态过滤苗木基地列表；没有数据时返回空页，不报错。"""
    if size > 200:
        raise HTTPException(status_code=400, detail="每页最多 200 条，请缩小分页范围")
    items, total = service.list_entries(keyword=keyword, variety=variety, status=status, page=page, size=size)
    return PageResult(items=items, total=total, page=page, size=size)


@router.get("/{entry_id}", response_model=dict)
def get_entry(entry_id: int) -> dict:
    """读取单条苗圃明细；不存在时给出可读的错误说明。"""
    entry = service.get_entry(entry_id)
    if entry is None:
        raise HTTPException(status_code=404, detail=f"苗圃 {entry_id} 不存在或已归档")
    return entry


@router.post("", response_model=ActionResult)
def create_entry(payload: EntryPayload) -> ActionResult:
    """登记一条苗圃，缺字段或编号重复时说明原因而不是静默丢弃。"""
    entry, missing = service.create_entry(payload.values)
    if missing:
        if missing == ["苗圃编号重复"]:
            return ActionResult(ok=False, message="该苗圃编号已存在，重复登记只认第一次的数据，未叠加")
        return ActionResult(ok=False, message=f"缺少必填字段或字段不合法：{'、'.join(missing)}")
    return ActionResult(ok=True, message="苗圃已登记", entry=entry)


@router.post("/{entry_id}/actions", response_model=ActionResult)
def run_action(entry_id: int, payload: EntryPayload) -> ActionResult:
    """对单条苗圃执行登记出圃、休整轮作、废弃苗圃；不允许的动作会被拦下并说明原因。"""
    action = str(payload.values.get("action") or "").strip()
    entry, message = service.run_action(entry_id, action)
    if entry is None:
        return ActionResult(ok=False, message=message)
    return ActionResult(ok=True, message=message, entry=entry)
