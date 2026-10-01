"""苗木数据准备流水线测试（只用标准库 unittest，不引入新依赖）。

运行：cd backend && python3 -m unittest discover -s tests -v
"""
from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

# 允许直接 python3 -m unittest 运行（不依赖第三方包，pipeline 本身只用标准库）。
BACKEND_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_DIR))

from app.seedling_pipeline import audit_log, manifest  # noqa: E402
from app.seedling_pipeline.catalog import VARIETIES, get_variety  # noqa: E402
from app.seedling_pipeline.importer import (  # noqa: E402
    apply_to_store,
    load_sample,
    quantity_fingerprint,
)
from app.seedling_pipeline.reconcile import reconcile  # noqa: E402
from app.seedling_pipeline.pipeline import prepare_seedlings  # noqa: E402

BAD_FIXTURE = BACKEND_DIR / "tests" / "fixtures" / "samples_bad.json"


class FakeStore:
    """最小内存仓库替身：实现 pipeline 用到的 rows(module)。"""

    def __init__(self) -> None:
        self._tables: dict[str, list[dict]] = {"seedling": []}

    def rows(self, module: str) -> list[dict]:
        return self._tables.setdefault(module, [])


class CatalogTests(unittest.TestCase):
    def test_baseline_is_cycle_times_batch(self):
        camphor = get_variety("香樟")
        self.assertEqual(camphor.in_nursery_baseline(), 200 * 12)
        osmanthus = get_variety("桂花")
        self.assertEqual(osmanthus.in_nursery_baseline(), 150 * 8)

    def test_known_varieties(self):
        self.assertEqual(set(VARIETIES), {"香樟", "桂花", "紫薇", "红花檵木", "银杏"})


class SampleTests(unittest.TestCase):
    def test_builtin_sample_is_self_consistent(self):
        entries, meta = load_sample()
        self.assertGreater(len(entries), 0)
        self.assertEqual(meta["variety_count"], 5)
        report = reconcile(entries)
        self.assertTrue(report.ok, [i.message for i in report.issues])

    def test_sample_grouped_by_variety_and_ordered(self):
        entries, meta = load_sample()
        varieties_in_order = [e["培育品种"] for e in entries]
        # 按品种名排序后拍平：品种分组段不逆序，且每个分组内记录连续
        self.assertEqual(varieties_in_order, sorted(varieties_in_order))
        self.assertEqual(len(set(varieties_in_order)), meta["variety_count"])
        # 所有培育品种都在口径表内
        self.assertTrue(all(e["培育品种"] in VARIETIES for e in entries))

    def test_fingerprint_stable(self):
        a, _ = load_sample()
        b, _ = load_sample()
        self.assertEqual(quantity_fingerprint(a)["checksum"], quantity_fingerprint(b)["checksum"])
        self.assertEqual(quantity_fingerprint(a)["total"],
                         quantity_fingerprint(a)["total_outplanted"]
                         + quantity_fingerprint(a)["total_in_nursery"])


class ReconcileBadFixtureTests(unittest.TestCase):
    def test_bad_fixture_is_rejected_with_codes(self):
        entries, _ = load_sample(BAD_FIXTURE)
        report = reconcile(entries)
        self.assertFalse(report.ok)
        self.assertEqual(set(report.mismatch_codes), {"BAD-001", "BAD-002", "BAD-003"})
        rules = {issue.rule for issue in report.issues}
        self.assertIn("出圃周期不符", rules)
        self.assertIn("在圃数量不自洽", rules)
        self.assertIn("数量不守恒", rules)
        self.assertIn("品种未登记", rules)


class IdempotentImportTests(unittest.TestCase):
    def test_duplicate_codes_not_doubled(self):
        entries, _ = load_sample()
        rows: list[dict] = []
        first = apply_to_store(entries, rows)
        second = apply_to_store(entries, rows)
        self.assertEqual(first["inserted"], len(entries))
        self.assertEqual(first["skipped"], 0)
        self.assertEqual(second["inserted"], 0)
        self.assertEqual(second["skipped"], len(entries))
        self.assertEqual(len(rows), len(entries))
        codes = [r["苗圃编号"] for r in rows]
        self.assertEqual(len(codes), len(set(codes)))


class PipelineGateTests(unittest.TestCase):
    def setUp(self):
        # 每个用例独立的台账与日志临时路径，避免污染真实运行产物。
        self.tmp = tempfile.TemporaryDirectory()
        self.tmpdir = Path(self.tmp.name)
        import app.seedling_pipeline.pipeline as pipeline_mod
        self.pipeline_mod = pipeline_mod
        self._orig_path = pipeline_mod.MANIFEST_PATH
        self._orig_log_dir = audit_log.LOG_DIR
        pipeline_mod.MANIFEST_PATH = self.tmpdir / "manifest.json"
        audit_log.LOG_DIR = self.tmpdir / "logs"

    def tearDown(self):
        self.pipeline_mod.MANIFEST_PATH = self._orig_path
        audit_log.LOG_DIR = self._orig_log_dir
        self.tmp.cleanup()

    def test_good_run_ready_and_idempotent(self):
        from app.seedling_pipeline.pipeline import load_into_store

        store = FakeStore()
        r1 = prepare_seedlings(store=store)
        self.assertTrue(r1.ok)
        self.assertTrue(r1.ready)
        n = len(store.rows("seedling"))
        self.assertGreater(n, 0)

        # 场景 A：模拟"重启换了一台机器/新进程"——从台账装载，数量与台账一致
        store2 = FakeStore()
        loaded = load_into_store(store2)
        self.assertEqual(loaded, n)
        self.assertEqual(len(store2.rows("seedling")), n)

        # 场景 B：再次跑同一批示例数据。台账里编号已存在 -> skipped 全部、不新增
        r2 = prepare_seedlings(store=store)
        self.assertTrue(r2.ready)
        self.assertEqual(len(store.rows("seedling")), n)
        self.assertEqual(r2.report["skipped"], n)
        self.assertEqual(r2.report["inserted"], 0)
        # 指纹跨运行一致 -> 换环境得到同一份
        self.assertEqual(r1.report["checksum"], r2.report["checksum"])

        # 场景 C：台账已装载过的 store 再 load 一次，也不叠加
        self.assertEqual(load_into_store(store), 0)
        self.assertEqual(len(store.rows("seedling")), n)

    def test_bad_run_not_ready_and_manifest_unchanged(self):
        mpath = self.pipeline_mod.MANIFEST_PATH
        # 先用好数据建立台账
        good_store = FakeStore()
        good = prepare_seedlings(store=good_store)
        good_entries = manifest.manifest_entries(mpath)
        self.assertTrue(good.ready)

        # 再跑坏批次：不 ready，台账不变
        bad_store = FakeStore()
        bad = prepare_seedlings(sample_path=BAD_FIXTURE, store=bad_store)
        self.assertTrue(bad.ok)               # 流程本身执行成功
        self.assertFalse(bad.ready)           # 但核对未通过，不算准备好
        self.assertEqual(len(manifest.manifest_entries(mpath)), len(good_entries))
        self.assertIn("BAD-001", bad.report["mismatch_codes"])

    def test_manifest_is_deterministic_bytes(self):
        mpath = self.pipeline_mod.MANIFEST_PATH
        prepare_seedlings(store=FakeStore())
        bytes_a = mpath.read_bytes()
        data = json.loads(bytes_a)
        # 用同样输入再写一次，应逐字节一致
        manifest.save_manifest(
            data["entries"], checksum=data["checksum"],
            meta={"version": data["data_version"], "source": data["source"]}, path=mpath,
        )
        self.assertEqual(bytes_a, mpath.read_bytes())


if __name__ == "__main__":
    unittest.main()
