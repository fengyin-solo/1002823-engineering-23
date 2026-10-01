"""苗木基地业务规则：状态流转、字段校验、筛选口径与数据准备流程入口都收在这里。"""
from __future__ import annotations

from typing import Any

from app.seedprep.dependencies import MissingDependency, check_dependencies, render_missing
from app.seedprep.paths import LOG_DIR
from app.seedprep.policy import (
    STATUS_ORDER,
    as_int,
    expected_in_nursery,
)
from app.seedprep.catalog import load_catalog
from app.seedprep.pipeline import load_status, run_pipeline
from app.store import store

MODULE = "seedling"
CODE_FIELD = "苗圃编号"
REQUIRED_FIELDS = ["苗圃编号", "苗圃名称", "苗圃面积", "培育品种", "培育数量", "出圃数量"]
ACTION_RULES = {"登记出圃": "出圃中", "休整轮作": "休整中", "废弃苗圃": "已废弃"}


class SeedlingService:
    def list_entries(
        self,
        *,
        keyword: str | None = None,
        variety: str | None = None,
        status: str | None = None,
        page: int = 1,
        size: int = 20,
    ) -> tuple[list[dict[str, Any]], int]:
        rows = store.rows(MODULE)
        if keyword:
            rows = [row for row in rows if keyword in str(row.get(CODE_FIELD, ""))]
        if variety:
            rows = [row for row in rows if variety in str(row.get("培育品种", ""))]
        if status:
            rows = [row for row in rows if row.get("status") == status]
        total = len(rows)
        start = max(page - 1, 0) * size
        return rows[start:start + size], total

    def get_entry(self, entry_id: int) -> dict[str, Any] | None:
        return store.find(MODULE, entry_id)

    def create_entry(self, values: dict[str, Any]) -> tuple[dict[str, Any] | None, list[str]]:
        missing = [field for field in REQUIRED_FIELDS if str(values.get(field) or "").strip() == ""]
        if missing:
            return None, missing

        code = str(values[CODE_FIELD]).strip()
        if store.find_by_code(MODULE, CODE_FIELD, code) is not None:
            # 运行期录入同样遵守「同一编号只认第一次」，不叠成两份
            return None, ["苗圃编号重复"]

        catalog = load_catalog()
        variety = str(values["培育品种"]).strip()
        raised = as_int(values.get("培育数量"))
        outplanted = as_int(values.get("出圃数量"))
        if raised is None or outplanted is None:
            return None, ["培育数量", "出圃数量"]
        if variety not in catalog:
            return None, ["培育品种"]

        rows = store.rows(MODULE)
        entry = {"id": max((int(row.get("id", 0)) for row in rows), default=0) + 1}
        entry.update({
            CODE_FIELD: code,
            "苗圃名称": str(values.get("苗圃名称", "")).strip(),
            "苗圃面积": values.get("苗圃面积", ""),
            "培育品种": variety,
            "出圃周期": catalog[variety],
            "培育数量": raised,
            "出圃数量": outplanted,
            # 在圃数量以出圃数量为准，口径只在 policy.py 一处
            "在圃数量": expected_in_nursery(raised, outplanted),
            "管护人员": str(values.get("管护人员", "")).strip(),
            "status": STATUS_ORDER[0],
            "pending": True,
            "abnormal": False,
        })
        rows.append(entry)
        store.persist_seedling()
        return entry, []

    def run_action(self, entry_id: int, action: str) -> tuple[dict[str, Any] | None, str]:
        entry = store.find(MODULE, entry_id)
        if entry is None:
            return None, f"苗圃 {entry_id} 不存在或已归档"
        if action not in ACTION_RULES:
            return None, f"动作「{action}」不属于苗木基地可执行范围"
        target = ACTION_RULES[action]
        entry["status"] = target
        entry["pending"] = target != STATUS_ORDER[-1]
        entry["abnormal"] = target == "出圃中"
        store.persist_seedling()
        return entry, f"苗圃已{action}"

    # ---- 数据准备流程 ----

    def prepare_status(self) -> dict[str, Any]:
        return load_status()

    def check_dependencies(self) -> list[MissingDependency]:
        return check_dependencies()

    def run_prepare(self) -> tuple[dict[str, Any], list[MissingDependency]]:
        """跑一遍数据准备流水线；依赖缺失时停在安装这一步，返回缺失说明。"""
        missing = check_dependencies()
        if missing:
            return {}, missing
        report = run_pipeline()
        store.reload_seedling()
        return report, []

    def latest_log(self) -> dict[str, Any]:
        """读取最近一次核对日志内容，页面上直接留档可见。"""
        latest = LOG_DIR / "latest.log"
        if not latest.exists():
            return {"has_log": False, "log_dir": "var/logs/seedling/", "content": ""}
        return {
            "has_log": True,
            "log_dir": "var/logs/seedling/",
            "content": latest.read_text(encoding="utf-8"),
        }

    @staticmethod
    def explain_missing(missing: list[MissingDependency]) -> str:
        return render_missing(missing)
