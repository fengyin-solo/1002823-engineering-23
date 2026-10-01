"""苗木基地接口：维护苗圃，覆盖登记出圃、休整轮作、废弃苗圃等动作。"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query

from app.schemas import ActionResult, EntryPayload, PageResult
from app.seedling_pipeline import audit_log
from app.seedling_pipeline.pipeline import current_status, prepare_seedlings
from app.services.seedling import SeedlingService
from app.store import store

router = APIRouter(prefix="/api/seedling", tags=["苗木基地"])

service = SeedlingService()

LIST_FIELDS = ["苗圃编号", "苗圃名称", "苗圃面积", "培育品种", "出圃周期", "出圃数量", "在圃数量", "计划总量", "管护人员", "苗圃状态"]
STATUSES = ["正常", "出圃中", "休整中", "已废弃"]


# ---- 数据准备（可重复流程）：这几个静态路由必须放在 /{entry_id} 之前，避免被当成编号 ----

@router.post("/prepare/run")
def run_prepare() -> dict[str, Any]:
    """（重新）执行一遍苗木数据准备：幂等导入示例数据并自动核对。

    重复执行同一批苗圃编号只认第一次；核对不通过时 ready=false，不算准备好。
    """
    result = prepare_seedlings(store=store)
    return {
        "ok": result.ok,
        "ready": result.ready,
        "message": result.message,
        "report": result.report,
    }


@router.get("/prepare/status")
def prepare_status() -> dict[str, Any]:
    """查看当前数据准备状态：是否就绪、数量指纹、对不上的编号等。"""
    return current_status(store=store)


@router.get("/prepare/log")
def prepare_log() -> dict[str, Any]:
    """读取最近一次核对日志（留档内容），供页面直接展示。"""
    text = audit_log.read_latest_log()
    latest = audit_log.load_latest()
    if text is None:
        return {"ran": False, "content": None, "message": "还没有核对日志，请先执行数据准备。"}
    return {
        "ran": True,
        "content": text,
        "ran_at": (latest or {}).get("ran_at"),
        "ready": (latest or {}).get("ready"),
        "log_file": (latest or {}).get("logs", {}).get("latest_log"),
    }


@router.get("", response_model=PageResult[dict])
def list_entries(
    keyword: str | None = Query(default=None, description="按苗圃编号检索"),
    status: str | None = Query(default=None, description="正常、出圃中、休整中、已废弃"),
    page: int = 1,
    size: int = 20,
) -> PageResult[dict]:
    """按苗圃编号与状态过滤苗木基地列表；没有数据时返回空页，不报错。"""
    if size > 200:
        raise HTTPException(status_code=400, detail="每页最多 200 条，请缩小分页范围")
    items, total = service.list_entries(keyword=keyword, status=status, page=page, size=size)
    return PageResult(items=items, total=total, page=page, size=size)


@router.get("/export")
def export_entries() -> dict[str, Any]:
    """导出苗木基地清单：返回当前过滤条件下的全量数据。"""
    items, total = service.list_entries(page=1, size=10000)
    return {"module": "seedling", "total": total, "items": items}


@router.get("/{entry_id}", response_model=dict)
def get_entry(entry_id: int) -> dict:
    """读取单条苗圃明细；不存在时给出可读的错误说明。"""
    entry = service.get_entry(entry_id)
    if entry is None:
        raise HTTPException(status_code=404, detail=f"苗圃 {entry_id} 不存在或已归档")
    return entry


@router.post("", response_model=ActionResult)
def create_entry(payload: EntryPayload) -> ActionResult:
    """登记一条苗圃，缺字段时说明原因而不是静默丢弃。"""
    entry, missing = service.create_entry(payload.values)
    if missing:
        return ActionResult(ok=False, message=f"缺少必填字段：{'、'.join(missing)}")
    return ActionResult(ok=True, message="苗圃已登记", entry=entry)


@router.post("/{entry_id}/actions", response_model=ActionResult)
def run_action(entry_id: int, payload: EntryPayload) -> ActionResult:
    """对单条苗圃执行登记出圃、休整轮作、废弃苗圃；不允许的动作会被拦下并说明原因。"""
    action = str(payload.values.get("action") or "").strip()
    entry, message = service.run_action(entry_id, action)
    if entry is None:
        return ActionResult(ok=False, message=message)
    return ActionResult(ok=True, message=message, entry=entry)
