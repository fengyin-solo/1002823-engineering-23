"""园林绿化养护管理平台 后端服务入口。

启动：uvicorn app.main:app --host 127.0.0.1 --port 8000
健康检查：GET /api/health
"""
from __future__ import annotations

import contextlib

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.routers import ROUTERS
from app.seedling_pipeline.pipeline import (
    current_status,
    load_into_store,
    prepare_seedlings,
)
from app.store import store

app = FastAPI(title="园林绿化养护管理平台", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

for module in ROUTERS:
    app.include_router(module.router)


@contextlib.asynccontextmanager
async def lifespan(_app: FastAPI):
    """启动即跑一遍可重复的数据准备。

    先从准备台账装载"上次已认下"的数据（跨重启/换机器得到同一批、同编号不叠加），
    再按示例数据跑一次核对：核对通过则增量并入新编号，核对不通过则保持台账不变、
    /api/health 如实显示未就绪。整个数据准备只用标准库。
    """
    load_into_store(store)
    prepare_seedlings(store=store)
    yield


app.router.lifespan_context = lifespan


@app.get("/api/health")
def health() -> dict[str, object]:
    """健康检查：确认服务已经监听，并反映苗木数据是否准备好。"""
    status = current_status(store=store)
    return {
        "ok": True,
        "app": settings.app_name,
        "modules": len(store.module_names()),
        "seedling_ready": status["ready"],
        "seedling": status,
    }


@app.get("/api/overview")
def overview() -> dict[str, object]:
    """运营概览：把各业务模块的待处理量汇总成看板卡片。"""
    return store.overview()
