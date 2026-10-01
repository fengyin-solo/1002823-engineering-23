"""内存数据仓库：给每个业务模块准备一份可筛选、可流转的示例数据。

真实项目里这里会换成数据库访问层；当前实现只依赖标准库，保证克隆下来就能起。

苗木基地（seedling）的数据来自数据准备流水线：优先用本机运行期文件
（页面上的登记 / 状态流转会落在这里），没有时用随仓库走的 prepared.json，
保证换台机器、重启服务取到的仍是同一份已核对数据。
"""
from __future__ import annotations

from typing import Any

from app.seed import SEED_ROWS
from app.seedprep.repository import load_prepared, load_working_store, save_working_store

SEEDLING_MODULE = "seedling"


def _seedling_rows() -> list[dict[str, Any]]:
    """苗木基地启动数据：本机运行期变更优先，其次流水线准备好的数据。"""
    working = load_working_store()
    if working:
        return [dict(row) for row in working]
    prepared = load_prepared()
    if prepared:
        return [dict(row) for row in prepared]
    return [dict(row) for row in SEED_ROWS.get(SEEDLING_MODULE, [])]


class Store:
    def __init__(self) -> None:
        self._tables: dict[str, list[dict[str, Any]]] = {
            name: [dict(row) for row in rows] for name, rows in SEED_ROWS.items()
        }
        self._tables[SEEDLING_MODULE] = _seedling_rows()

    def module_names(self) -> list[str]:
        return sorted(self._tables)

    def rows(self, module: str) -> list[dict[str, Any]]:
        return self._tables.setdefault(module, [])

    def find(self, module: str, entry_id: int) -> dict[str, Any] | None:
        for row in self.rows(module):
            if int(row.get("id", 0)) == entry_id:
                return row
        return None

    def find_by_code(self, module: str, code_field: str, code: str) -> dict[str, Any] | None:
        """按业务编号查记录；数据准备流程的「编号唯一、只认第一次」在运行期也生效。"""
        target = str(code).strip()
        for row in self.rows(module):
            if str(row.get(code_field, "")).strip() == target:
                return row
        return None

    def reload_seedling(self) -> None:
        """数据准备流程跑完后，把流水线产物重新装载进内存（保留本机运行期变更）。"""
        self._tables[SEEDLING_MODULE] = _seedling_rows()

    def persist_seedling(self) -> None:
        """把苗木基地当前状态落到本机运行期文件，重启 / 换机器动作不丢。"""
        save_working_store(self.rows(SEEDLING_MODULE))

    def overview(self) -> dict[str, object]:
        modules: list[dict[str, object]] = []
        for name in self.module_names():
            rows = self.rows(name)
            modules.append({
                "name": name,
                "created": len(rows),
                "pending": sum(1 for row in rows if row.get("pending")),
                "abnormal": sum(1 for row in rows if row.get("abnormal")),
            })
        cards = [
            {"label": "业务模块", "value": len(modules)},
            {"label": "今日新增", "value": sum(int(item["created"]) for item in modules)},
            {"label": "待处理", "value": sum(int(item["pending"]) for item in modules)},
            {"label": "异常量", "value": sum(int(item["abnormal"]) for item in modules)},
        ]
        return {"cards": cards, "modules": modules}


store = Store()
