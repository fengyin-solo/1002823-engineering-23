"""数据准备流水线编排：读取 -> 幂等导入 -> 自动核对 -> 就绪闸门 -> 台账/日志留档。

对外只暴露 prepare_seedlings() / current_status() / last_report() / load_into_store()。

幂等与"同一份"如何保证：
- 核对通过的标准数据会写入准备台账 manifest（确定性 JSON），跨进程/跨机器一致；
- 每次启动先 load_into_store() 从台账装载到内存仓库；
- 再次 prepare 时，台账里已有的苗圃编号视为第一次已认下，新数据里同编号一律跳过，
  只有全新编号会被并入，绝不会叠成两份；
- 核对不通过时 ready 恒为 False，且不改动台账与运行仓库（不算准备好）。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from app.seedling_pipeline import audit_log, manifest
from app.seedling_pipeline.catalog import QUANTITY_AUTHORITY, VARIETIES
from app.seedling_pipeline.importer import (
    SampleDataError,
    apply_to_store,
    load_sample,
    quantity_fingerprint,
)
from app.seedling_pipeline.reconcile import KEY_CODE, reconcile

MODULE = "seedling"

# 台账路径默认指向运行产物目录；测试可直接改写它以隔离产物。
MANIFEST_PATH: Path | None = None


@dataclass
class PipelineResult:
    ok: bool                  # 流水线是否成功执行（数据文件可读取）
    ready: bool               # 核对是否通过、数据是否"准备好"
    message: str
    report: dict[str, Any] = field(default_factory=dict)


def load_into_store(store) -> int:
    """用准备台账把内存仓库装载成"已认下"的数据。启动时调用。

    返回装载条数；台账不存在时返回 0。幂等：仓库里已有的编号不会重复加。
    """
    entries = manifest.manifest_entries(MANIFEST_PATH)
    if not entries:
        return 0
    return apply_to_store(entries, store.rows(MODULE))["inserted"]


def _per_variety(entries: list[dict[str, Any]]) -> dict[str, dict[str, int]]:
    per_variety: dict[str, dict[str, int]] = {}
    for e in entries:
        name = str(e.get("培育品种") or "未分类")
        bucket = per_variety.setdefault(name, {"nurseries": 0, "出圃数量": 0, "在圃数量": 0})
        bucket["nurseries"] += 1
        bucket["出圃数量"] += int(e.get("出圃数量") or 0)
        bucket["在圃数量"] += int(e.get("在圃数量") or 0)
    return per_variety


def _build_report(
    *,
    entries: list[dict[str, Any]],
    meta: dict[str, Any],
    reconcile_report,
    inserted: int,
    skipped: int,
    ran_at: str,
) -> dict[str, Any]:
    fingerprint = quantity_fingerprint(entries)
    ready = reconcile_report.ok
    return {
        "ran_at": ran_at,
        "ready": ready,
        "ok": True,
        "data_version": meta.get("version"),
        "source": meta.get("source"),
        "variety_count": meta.get("variety_count"),
        "varieties": meta.get("varieties"),
        "per_variety": _per_variety(entries),
        "authority": QUANTITY_AUTHORITY,
        "inserted": inserted,
        "skipped": skipped,
        **fingerprint,
        **reconcile_report.to_dict(),
    }


def prepare_seedlings(*, sample_path: Path | str | None = None, store=None) -> PipelineResult:
    """执行一次完整的数据准备。可重复执行、跨进程幂等。

    store 默认可省略（只做核对与台账维护）；传入内存仓库时会同步装载/增量更新。
    """
    ran_at = datetime.now().strftime("%Y-%m-%dT%H:%M:%S")

    try:
        entries, meta = load_sample(sample_path)
    except SampleDataError as exc:
        report = {
            "ran_at": ran_at, "ok": False, "ready": False,
            "message": str(exc), "checked": 0, "mismatch_codes": [],
            "issues": [], "authority": QUANTITY_AUTHORITY,
        }
        audit_log.archive(report)
        return PipelineResult(False, False, f"数据准备失败：{exc}", report)

    # 1) 先核对示例数据本身；不通过就不进"已就绪"，台账与运行仓库都不动。
    reconcile_report = reconcile(entries)
    if not reconcile_report.ok:
        report = _build_report(
            entries=entries, meta=meta, reconcile_report=reconcile_report,
            inserted=0, skipped=0, ran_at=ran_at,
        )
        paths = audit_log.archive(report)
        report["logs"] = paths
        codes = "、".join(reconcile_report.mismatch_codes) or "无"
        return PipelineResult(
            True, False,
            f"核对未通过，数据不算准备好。对不上的苗圃编号：{codes}；"
            f"详见核对日志 {paths['latest_log']}",
            report,
        )

    # 2) 与台账合并：台账里已有的编号只认第一次（跳过），全新编号才并入。
    existing_entries = manifest.manifest_entries(MANIFEST_PATH)
    existing_codes = {str(e.get(KEY_CODE)) for e in existing_entries}
    fresh = [e for e in entries if str(e.get(KEY_CODE)) not in existing_codes]
    skipped = len(entries) - len(fresh)

    if fresh:
        merged = existing_entries + fresh
        fingerprint = quantity_fingerprint(merged)["checksum"]
        manifest.save_manifest(merged, checksum=fingerprint, meta=meta, path=MANIFEST_PATH)

    # 3) 同步运行仓库（同样按编号幂等）。store_loaded 是相对本次内存仓库的装载条数，
    #    与上面相对台账的 new/skipped 是两个不同基准，分开记录避免混在一个数字里。
    store_loaded = 0
    if store is not None:
        store_loaded = apply_to_store(entries, store.rows(MODULE))["inserted"]

    # 报告以"当前这批示例数据"为准统计数量（同一份数据，指纹稳定）。
    report = _build_report(
        entries=entries, meta=meta, reconcile_report=reconcile_report,
        inserted=len(fresh), skipped=skipped, ran_at=ran_at,
    )
    report["new_codes"] = len(fresh)
    report["store_loaded"] = store_loaded
    report["manifest_nurseries"] = len(manifest.manifest_entries(MANIFEST_PATH))
    paths = audit_log.archive(report)
    report["logs"] = paths

    message = (
        f"数据已准备好：{report['nurseries']} 个苗圃、{report['variety_count']} 个培育品种，"
        f"本次认下新编号 {len(fresh)} 个、重复编号跳过 {skipped} 个，核对全部通过。"
    )
    return PipelineResult(True, True, message, report)


def last_report() -> dict[str, Any] | None:
    """最近一次准备结果（结构化）。"""
    return audit_log.load_latest()


def current_status(store=None) -> dict[str, Any]:
    """供接口/健康检查读取的当前准备状态。从未跑过流水线时 ready=False。"""
    latest = audit_log.load_latest()
    running_rows = len(store.rows(MODULE)) if store is not None else None
    if latest is None:
        return {
            "ready": False,
            "ran": False,
            "message": "尚未执行数据准备，请先跑苗木数据准备流程。",
            "running_rows": running_rows,
            "authority": QUANTITY_AUTHORITY,
            "known_varieties": sorted(VARIETIES),
        }
    return {
        "ready": bool(latest.get("ready")),
        "ran": True,
        "ok": bool(latest.get("ok", True)),
        "ran_at": latest.get("ran_at"),
        "message": "核对通过，数据已就绪。" if latest.get("ready") else "核对未通过，数据不算准备好。",
        "checksum": latest.get("checksum"),
        "data_version": latest.get("data_version"),
        "variety_count": latest.get("variety_count"),
        "nurseries": latest.get("nurseries"),
        "total_outplanted": latest.get("total_outplanted"),
        "total_in_nursery": latest.get("total_in_nursery"),
        "total": latest.get("total"),
        "per_variety": latest.get("per_variety"),
        "mismatch_codes": latest.get("mismatch_codes", []),
        "inserted": latest.get("inserted"),
        "skipped": latest.get("skipped"),
        "manifest_nurseries": latest.get("manifest_nurseries"),
        "running_rows": running_rows,
        "authority": QUANTITY_AUTHORITY,
        "known_varieties": sorted(VARIETIES),
    }
