"""苗木基地数据准备流水线的单元测试（标准库 unittest，不引第三方依赖）。

运行：cd backend && .venv/bin/python -m unittest discover -s tests -v
"""
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from app.seedprep.dependencies import check_dependencies
from app.seedprep.pipeline import run_pipeline
from app.seedprep.policy import QUANTITY_RULE_SOURCE, expected_in_nursery
from app.seedprep.validation import reconcile

CATALOG = {"香樟": 730, "紫薇": 365}

VALID_ROWS = [
    {"苗圃编号": "X-01", "苗圃名称": "甲", "培育品种": "香樟", "出圃周期": 730,
     "培育数量": 100, "出圃数量": 30, "在圃数量": 70},
    {"苗圃编号": "X-02", "苗圃名称": "乙", "培育品种": "紫薇", "出圃周期": 365,
     "培育数量": 200, "出圃数量": 50, "在圃数量": 150},
]


def write_fixture(root: Path) -> tuple[Path, Path, Path, Path]:
    """造一套临时的数据准备目录，测试间互不干扰、不碰真实 data/ 与 var/。"""
    samples = root / "samples"
    prepared = root / "prepared.json"
    report = root / "report.json"
    logs = root / "logs"
    samples.mkdir(parents=True)
    (root / "catalog.json").write_text(
        json.dumps({"品种目录": [
            {"培育品种": "香樟", "出圃周期": 730},
            {"培育品种": "紫薇", "出圃周期": 365},
        ]}),
        encoding="utf-8",
    )
    return samples, prepared, report, logs


class PolicyTest(unittest.TestCase):
    def test_quantity_source_is_outplanted(self):
        # 口径写死在 policy 一处：以出圃数量为准
        self.assertEqual(QUANTITY_RULE_SOURCE, "出圃数量")
        self.assertEqual(expected_in_nursery(100, 30), 70)


class ReconcileTest(unittest.TestCase):
    def test_valid_rows_pass(self):
        result = reconcile([dict(row) for row in VALID_ROWS], CATALOG)
        self.assertTrue(result.passed)
        self.assertEqual(len(result.valid_rows), 2)
        self.assertEqual(result.mismatches, [])

    def test_in_nursery_mismatch_lists_code(self):
        rows = [dict(VALID_ROWS[0])]
        rows[0]["在圃数量"] = 99  # 100-30=70，对不上
        result = reconcile(rows, CATALOG)
        self.assertFalse(result.passed)
        self.assertEqual(result.mismatches[0].code, "X-01")
        self.assertEqual(result.mismatches[0].kind, "在圃数量")
        self.assertIn("以出圃数量为准", result.mismatches[0].detail)

    def test_cycle_mismatch_lists_code(self):
        rows = [dict(VALID_ROWS[0])]
        rows[0]["出圃周期"] = 365  # 香樟目录标准是 730
        result = reconcile(rows, CATALOG)
        self.assertFalse(result.passed)
        self.assertEqual(result.mismatches[0].code, "X-01")
        self.assertEqual(result.mismatches[0].kind, "出圃周期")

    def test_outplanted_exceeds_raised(self):
        rows = [dict(VALID_ROWS[0])]
        rows[0]["出圃数量"], rows[0]["在圃数量"] = 130, -30
        result = reconcile(rows, CATALOG)
        kinds = {item.kind for item in result.mismatches}
        self.assertIn("数量关系", kinds)

    def test_unknown_variety(self):
        rows = [dict(VALID_ROWS[0])]
        rows[0]["培育品种"] = "不存在的品种"
        result = reconcile(rows, CATALOG)
        self.assertFalse(result.passed)
        self.assertEqual(result.mismatches[0].kind, "培育品种")

    def test_missing_required_field(self):
        rows = [dict(VALID_ROWS[0])]
        del rows[0]["苗圃编号"]
        result = reconcile(rows, CATALOG)
        self.assertFalse(result.passed)
        self.assertEqual(result.mismatches[0].kind, "必填字段")

    def test_duplicate_code_only_first_counts(self):
        rows = [dict(VALID_ROWS[0]), dict(VALID_ROWS[0])]
        rows[1]["在圃数量"] = 1  # 第二次即便数据对不上也不参与核对
        result = reconcile(rows, CATALOG)
        self.assertTrue(result.passed)
        self.assertEqual(len(result.valid_rows), 1)
        self.assertEqual(len(result.skipped_duplicates), 1)
        self.assertEqual(result.skipped_duplicates[0]["苗圃编号"], "X-01")

    def test_file_variety_mismatch_reported(self):
        from app.seedprep.catalog import load_samples

        with tempfile.TemporaryDirectory() as tmp:
            samples = Path(tmp) / "samples"
            samples.mkdir()
            (samples / "香樟.json").write_text(
                json.dumps([{**VALID_ROWS[0], "培育品种": "紫薇"}], ensure_ascii=False),
                encoding="utf-8",
            )
            rows, errors = load_samples(samples)
            result = reconcile(rows, CATALOG, load_errors=errors)
            self.assertTrue(any("不一致" in item.detail for item in result.mismatches))


class PipelineTest(unittest.TestCase):
    def test_pipeline_passes_and_imports(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            samples, prepared, report, logs = write_fixture(root)
            (samples / "香樟.json").write_text(json.dumps([VALID_ROWS[0]], ensure_ascii=False), encoding="utf-8")
            (samples / "紫薇.json").write_text(json.dumps([VALID_ROWS[1]], ensure_ascii=False), encoding="utf-8")

            result = run_pipeline(samples_dir=samples, prepared_path=prepared, report_path=report, log_dir=logs)
            self.assertTrue(result["ready"])
            self.assertEqual(result["导入"]["准备总数"], 2)
            self.assertEqual(result["数量汇总"]["在圃数量"], 220)
            self.assertTrue(prepared.exists())
            self.assertTrue(any(logs.glob("prepare-*.log")))

            doc = json.loads(prepared.read_text(encoding="utf-8"))
            self.assertEqual(doc["数量口径"], "出圃数量")

    def test_pipeline_deterministic_across_runs(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            samples, prepared, report, logs = write_fixture(root)
            another = dict(VALID_ROWS[0])
            another["苗圃编号"] = "X-03"
            another["培育数量"], another["出圃数量"], another["在圃数量"] = 50, 10, 40
            (samples / "香樟.json").write_text(
                json.dumps([VALID_ROWS[0], another], ensure_ascii=False), encoding="utf-8"
            )

            first = run_pipeline(samples_dir=samples, prepared_path=prepared, report_path=report, log_dir=logs)
            prepared_after_first = prepared.read_bytes()
            second = run_pipeline(samples_dir=samples, prepared_path=prepared, report_path=report, log_dir=logs)

            # 同一套流程跑两遍：数量一份、签名一份、prepared.json 字节级一致
            self.assertEqual(first["signature"], second["signature"])
            self.assertEqual(second["导入"]["准备总数"], 2)
            self.assertEqual(second["导入"]["本次新增编号"], [])
            self.assertEqual(len(second["导入"]["已存在编号"]), 2)
            self.assertEqual(prepared_after_first, prepared.read_bytes())

    def test_pipeline_failure_does_not_import(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            samples, prepared, report, logs = write_fixture(root)
            bad = [dict(VALID_ROWS[0])]
            bad[0]["在圃数量"] = 999
            (samples / "香樟.json").write_text(json.dumps(bad, ensure_ascii=False), encoding="utf-8")

            result = run_pipeline(samples_dir=samples, prepared_path=prepared, report_path=report, log_dir=logs)
            self.assertFalse(result["ready"])
            self.assertEqual(len(result["核对不通过"]), 1)
            self.assertEqual(result["核对不通过"][0]["苗圃编号"], "X-01")
            self.assertFalse(prepared.exists())  # 核对不通过：不导入、不算准备好

            report_doc = json.loads(report.read_text(encoding="utf-8"))
            self.assertFalse(report_doc["ready"])

    def test_new_variety_appended_after_rerun(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            samples, prepared, report, logs = write_fixture(root)
            (samples / "香樟.json").write_text(json.dumps([VALID_ROWS[0]], ensure_ascii=False), encoding="utf-8")
            first = run_pipeline(samples_dir=samples, prepared_path=prepared, report_path=report, log_dir=logs)
            self.assertEqual(first["导入"]["准备总数"], 1)

            (samples / "紫薇.json").write_text(json.dumps([VALID_ROWS[1]], ensure_ascii=False), encoding="utf-8")
            second = run_pipeline(samples_dir=samples, prepared_path=prepared, report_path=report, log_dir=logs)
            self.assertTrue(second["ready"])
            self.assertEqual(second["导入"]["准备总数"], 2)
            self.assertEqual(second["导入"]["已存在编号"], ["X-01"])
            self.assertEqual(second["导入"]["本次新增编号"], ["X-02"])

    def test_within_batch_duplicate_not_doubled(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            samples, prepared, report, logs = write_fixture(root)
            (samples / "香樟.json").write_text(
                json.dumps([VALID_ROWS[0], VALID_ROWS[0]], ensure_ascii=False), encoding="utf-8"
            )
            result = run_pipeline(samples_dir=samples, prepared_path=prepared, report_path=report, log_dir=logs)
            self.assertTrue(result["ready"])
            self.assertEqual(result["导入"]["准备总数"], 1)
            self.assertEqual(len(result["去重跳过"]), 1)


class DependencyTest(unittest.TestCase):
    def test_current_env_complete(self):
        # 开发机与 CI 装完 requirements 后应无缺失
        self.assertEqual(check_dependencies(), [])

    def test_missing_requirements_listed(self):
        with tempfile.TemporaryDirectory() as tmp:
            missing = check_dependencies(Path(tmp))
            self.assertTrue(any(item.name == "requirements.txt" for item in missing))
            for item in missing:
                self.assertTrue(item.install)


if __name__ == "__main__":
    unittest.main()
