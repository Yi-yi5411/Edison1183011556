# -*- coding: utf-8 -*-
"""识别记忆体系单元测试：记忆沉淀 / 召回注入 / 上下文压缩。

覆盖范围：
- 存储层：scan_memory 表读写、同键合并计数、清空；
- 沉淀：learn_from_correction（对齐行按列差分、上限、开关）、
        learn_patterns（仅量程治理"自动清空"留痕）；
- 注入：recall_hints / remember_session / recall_session / compose_hints
        （短期在前、命中计数、异常静默降级），以及流水线 ExtractStep
        与智能体 build_repair_prompt 的注入透传；
- 压缩：max_hints 截断 + "另有N处零星历史修正"摘要折叠、
        短期会话 LRU 淘汰与 TTL 过期。

运行方式（项目根目录）：
    python test_memory.py -v
"""
import os
import shutil
import sys
import tempfile
import time
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from report_generator.scan_recognition.config import Config
from report_generator.scan_recognition.storage import ScanDatabase
from report_generator.scan_recognition.agent.memory import MemoryStore
from report_generator.scan_recognition.pipeline import (
    ExtractStep, ScanRecognitionPipeline)


class _TempDbCase(unittest.TestCase):
    """每个用例独立的临时数据库与目录，互不污染真实数据。"""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp(prefix="test_memory_")
        self.db = ScanDatabase(db_path=os.path.join(self.tmpdir, "mem.db"))

    def tearDown(self):
        self.db.close()
        shutil.rmtree(self.tmpdir, ignore_errors=True)


# ── 一、记忆沉淀：存储层 ──
class TestStorageDeposition(_TempDbCase):

    def test_same_key_merges_count(self):
        """同一（项目,字段,原值,新值）重复记录只累加次数不新增行。"""
        self.db.remember_correction("回弹法", "回弹值", "33", "35")
        self.db.remember_correction("回弹法", "回弹值", "33", "35")
        items = self.db.list_memory("回弹法")
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["count"], 2)

    def test_list_memory_count_desc_and_filter(self):
        """列表按出现次数降序，可按检测项目过滤。"""
        self.db.remember_correction("回弹法", "回弹值", "1", "2")
        self.db.remember_correction("回弹法", "轴线编号", "11A", "1/A")
        self.db.remember_correction("回弹法", "轴线编号", "11A", "1/A")
        self.db.remember_correction("钻芯法", "直径", "70", "")
        items = self.db.list_memory("回弹法")
        self.assertEqual(len(items), 2)
        self.assertEqual(items[0]["field"], "轴线编号")
        self.assertEqual(items[0]["count"], 2)
        self.assertEqual(len(self.db.list_memory()), 3)
        self.assertEqual(self.db.list_memory()[0]["count"], 2)

    def test_pattern_kind_stored(self):
        """治理留痕以 kind=pattern 存储（新值为空）。"""
        self.db.remember_correction("钻芯法", "实测值1", "9", "",
                                    kind="pattern", note="未测")
        m = self.db.list_memory("钻芯法")[0]
        self.assertEqual(m["kind"], "pattern")
        self.assertEqual(m["old_value"], "9")
        self.assertEqual(m["new_value"], "")

    def test_memory_count_and_clear(self):
        self.db.remember_correction("A", "f", "1", "2")
        self.db.remember_correction("B", "f", "3", "4")
        self.assertEqual(self.db.memory_count(), 2)
        self.db.clear_memory()
        self.assertEqual(self.db.memory_count(), 0)


# ── 二、记忆沉淀：学习策略 ──
class TestLearning(_TempDbCase):

    def setUp(self):
        super().setUp()
        self.ms = MemoryStore(self.db, Config())

    def test_learn_only_diff_cells(self):
        """只学习差异格：同行同值格、双空格不计。"""
        cols = ["构件名称", "回弹值", "碳化深度"]
        old = [["1F梁", "33.2", "1.5"], ["2F梁", "/", "/"]]
        new = [["1F梁", "35.2", "1.5"], ["2F梁", "/", "/"]]
        n = self.ms.learn_from_correction("回弹法", cols, old, new)
        self.assertEqual(n, 1)
        m = self.db.list_memory("回弹法")[0]
        self.assertEqual((m["field"], m["old_value"], m["new_value"]),
                         ("回弹值", "33.2", "35.2"))

    def test_learn_row_mismatch_robust(self):
        """行数/列数不齐时安全跳过，不抛异常。"""
        n = self.ms.learn_from_correction(
            "回弹法", ["a", "b"], [["1"]], [["2", "3"], ["4", "5"]])
        self.assertEqual(n, 2)  # 第一行 b 列 ""→3，第二行 a→4 b→5

    def test_learn_limit_30(self):
        """单次校正最多学习 30 条，防止批量误操作灌爆记忆。"""
        old = [[str(i)] for i in range(40)]
        new = [[str(i + 1)] for i in range(40)]
        n = self.ms.learn_from_correction("回弹法", ["序号"], old, new)
        self.assertEqual(n, MemoryStore.LEARN_LIMIT)

    def test_learn_disabled(self):
        ms = MemoryStore(self.db, Config({"memory": {"enabled": False}}))
        self.assertEqual(ms.learn_from_correction(
            "X", ["a"], [["1"]], [["2"]]), 0)
        self.assertEqual(ms.learn_patterns("X", []), 0)
        self.assertEqual(ms.recall_hints("X"), "")

    def test_learn_patterns_only_auto_cleared(self):
        """仅"自动清空"类问题学习为未测模式，其余复核提示不沉淀。"""
        warnings = [
            {"行": 2, "字段": "实测值1", "值": "3",
             "问题": "小于合理量程，已按未测（/）自动清空，请确认"},
            {"行": 3, "字段": "轴线编号", "值": "11A",
             "问题": "轴线编号疑似丢失斜杠，请复核"},
        ]
        n = self.ms.learn_patterns("回弹法", warnings)
        self.assertEqual(n, 1)
        m = self.db.list_memory("回弹法")[0]
        self.assertEqual(m["kind"], "pattern")
        self.assertEqual((m["field"], m["old_value"]), ("实测值1", "3"))


# ── 三、召回注入 ──
class TestRecallInjection(_TempDbCase):

    def setUp(self):
        super().setUp()
        self.ms = MemoryStore(self.db, Config())
        self.ms.learn_from_correction("回弹法", ["回弹值"], [["33"]], [["35"]])

    def test_recall_hints_content(self):
        text = self.ms.recall_hints("回弹法")
        self.assertTrue(text.startswith("历史校正经验"))
        self.assertIn("回弹值", text)
        self.assertIn("33", text)
        self.assertIn("35", text)
        # 必须带免责声明，禁止模型照抄经验值
        self.assertIn("禁止照抄经验值", text)

    def test_recall_hints_empty_for_unknown_item(self):
        self.assertEqual(self.ms.recall_hints("不存在项目"), "")

    def test_session_roundtrip(self):
        hints = [{"行": 2, "字段": "实测值1", "值": "3", "问题": "x"}]
        self.ms.remember_session("hash1", hints, summary="识别2条")
        sess = self.ms.recall_session("hash1")
        self.assertIsNotNone(sess)
        self.assertEqual(sess["hints"][0]["字段"], "实测值1")
        self.assertEqual(sess["summary"], "识别2条")

    def test_session_ttl_expiry(self):
        self.ms.remember_session("hash1", [])
        self.ms._session["hash1"]["ts"] = \
            time.time() - MemoryStore.SESSION_TTL - 1
        self.assertIsNone(self.ms.recall_session("hash1"))
        self.assertNotIn("hash1", self.ms._session)  # 过期即清除

    def test_session_disabled(self):
        ms = MemoryStore(self.db, Config({"memory": {"session_cache": False}}))
        ms.remember_session("k", [{"行": 1}])
        self.assertIsNone(ms.recall_session("k"))

    def test_compose_short_term_first(self):
        """合并注入：短期会话留痕在前，长期校正经验在后。"""
        self.ms.remember_session("hashX", [
            {"行": 5, "字段": "回弹值", "值": "9", "问题": "可疑"}])
        text, hits = self.ms.compose_hints("回弹法", "hashX")
        self.assertLess(text.find("上次识别本图的复核留痕"),
                        text.find("历史校正经验"))
        self.assertIn("可疑", text)
        self.assertEqual(hits, 2)  # 短期1条 + 长期1条

    def test_compose_empty_when_nothing(self):
        self.assertEqual(self.ms.compose_hints("无", "无"), ("", 0))

    def test_compose_silent_degradation_without_db(self):
        """记忆不可用（db=None）时静默降级，绝不影响识别主流程。"""
        ms = MemoryStore(None, Config())
        self.assertEqual(ms.compose_hints("回弹法", "hash"), ("", 0))


# ── 四、上下文压缩 ──
class TestCompression(_TempDbCase):

    def setUp(self):
        super().setUp()
        self.ms = MemoryStore(self.db, Config({"memory": {"max_hints": 8}}))
        self.ms.learn_from_correction("回弹法", ["回弹值"], [["33"]], [["35"]])
        self.ms.learn_from_correction("回弹法", ["碳化深度"], [["1"]], [["2"]])

    def test_recall_hints_max_hints_cap_and_fold(self):
        """超过 max_hints 只注入前 N 条，其余折叠为一句摘要。"""
        db = ScanDatabase(db_path=os.path.join(self.tmpdir, "c1.db"))
        ms = MemoryStore(db, Config({"memory": {"max_hints": 3}}))
        for i in range(6):
            db.remember_correction("回弹法", "碳化深度", f"1.{i}", f"2.{i}")
        text = ms.recall_hints("回弹法")
        self.assertEqual(text.count("- 字段"), 3)
        self.assertIn("另有3处零星历史修正", text)
        db.close()

    def test_recall_hints_no_fold_under_limit(self):
        """记忆条数不超过 max_hints 时全部注入，无折叠摘要。"""
        text = self.ms.recall_hints("回弹法")
        self.assertEqual(text.count("- 字段"), 2)
        self.assertNotIn("零星历史修正", text)

    def test_session_lru_eviction(self):
        """短期记忆超容量按 LRU 淘汰最旧。"""
        for i in range(MemoryStore.SESSION_CAPACITY + 2):
            self.ms.remember_session(f"h{i}", [])
        self.assertEqual(len(self.ms._session), MemoryStore.SESSION_CAPACITY)
        self.assertNotIn("h0", self.ms._session)
        self.assertNotIn("h1", self.ms._session)
        self.assertIn(f"h{MemoryStore.SESSION_CAPACITY + 1}",
                      self.ms._session)

    def test_session_lru_refresh_keeps_recent(self):
        """重新写入刷新时间戳：后续少量新键只挤掉更旧的键。"""
        self.ms.remember_session("keep", [])
        for i in range(MemoryStore.SESSION_CAPACITY):
            self.ms.remember_session(f"n{i}", [])
        # 满容量时 keep 已被淘汰，重新写入视为最新
        self.ms.remember_session("keep", [])
        # 再来 CAPACITY-1 个新键：只挤掉 n0..n6，keep 仍存活
        for i in range(MemoryStore.SESSION_CAPACITY - 1):
            self.ms.remember_session(f"m{i}", [])
        self.assertIn("keep", self.ms._session)
        self.assertNotIn("n0", self.ms._session)


# ── 五、流水线与智能体注入透传 ──
class _FakeVisionExtractor:
    """桩视觉抽取器：记录收到的 hints，返回固定记录。"""

    vision_model = "fake-vlm"

    def __init__(self):
        self.seen_hints = None

    def resolve_vision_model(self):
        return "fake-vlm"

    def extract_vision(self, image_path, columns, hints=""):
        self.seen_hints = hints
        return [{"构件名称": "1F梁", "回弹值": "35"}]


class TestPipelineInjection(_TempDbCase):

    def setUp(self):
        super().setUp()
        self.png = os.path.join(self.tmpdir, "fake.png")
        with open(self.png, "wb") as f:
            f.write(b"\x89PNG\r\n\x1a\n" + b"0" * 64)
        self.pipe = ScanRecognitionPipeline(
            cfg=Config(), db=ScanDatabase(
                db_path=os.path.join(self.tmpdir, "pipe.db")))
        self.pipe.memory.learn_from_correction(
            "回弹法", ["回弹值"], [["33"]], [["35"]])
        self.ex = _FakeVisionExtractor()
        self.pipe._extractor = self.ex
        self.ctx = {"detection_item": "回弹法", "sub_item": "回弹法",
                    "columns": ["构件名称", "回弹值"], "file_hash": "hashP",
                    "stored_path": self.png, "source_path": self.png}

    def tearDown(self):
        self.pipe.db.close()
        super().tearDown()

    def test_extract_step_injects_hints(self):
        """ExtractStep 视觉路径召回记忆并传给 extract_vision。"""
        ExtractStep(self.pipe).execute(self.ctx)
        self.assertIsNotNone(self.ex.seen_hints)
        self.assertIn("历史校正经验", self.ex.seen_hints)
        self.assertIn("禁止照抄经验值", self.ex.seen_hints)
        self.assertGreaterEqual(self.ctx.get("memory_hits", 0), 1)

    def test_extract_step_snapshot_shows_memory(self):
        ExtractStep(self.pipe).execute(self.ctx)
        snap = ExtractStep(self.pipe).snapshot(self.ctx)
        self.assertGreaterEqual(snap.get("memory_hits", 0), 1)
        self.assertIn("历史校正经验", snap.get("memory_hints", ""))

    def test_extract_step_skips_on_override(self):
        """structured_override（离线/重放）路径不注入、不调视觉模型。"""
        self.ctx["structured_override"] = [{"构件名称": "1F梁"}]
        ExtractStep(self.pipe).execute(self.ctx)
        self.assertIsNone(self.ex.seen_hints)
        self.assertEqual(self.ctx["structured"], [{"构件名称": "1F梁"}])

    def test_repair_prompt_contains_memory(self):
        """智能体修复提示词注入记忆文本。"""
        from report_generator.scan_recognition.agent.nodes import \
            build_repair_prompt
        hints = [{"行": 1, "字段": "A", "值": "x", "问题": "y"}]
        p = build_repair_prompt(["A"], hints, memory_hints="记忆标记XYZ")
        self.assertIn("记忆标记XYZ", p)
        self.assertIn("重新逐格核对", p)  # 修复指令仍在

    def test_repair_prompt_memory_before_instructions(self):
        """记忆置于修复指令之前（经验供对照，指令最后强调）。"""
        from report_generator.scan_recognition.agent.nodes import \
            build_repair_prompt
        hints = [{"行": 1, "字段": "A", "值": "x", "问题": "y"}]
        p = build_repair_prompt(["A"], hints, memory_hints="记忆标记XYZ")
        self.assertLess(p.find("记忆标记XYZ"), p.find("修正要求"))

    def test_repair_prompt_without_memory(self):
        """不传记忆时提示词保持原样（无记忆段落）。"""
        from report_generator.scan_recognition.agent.nodes import \
            build_repair_prompt
        p = build_repair_prompt(["A"], [])
        self.assertNotIn("历史校正经验", p)


if __name__ == "__main__":
    unittest.main(verbosity=2)
