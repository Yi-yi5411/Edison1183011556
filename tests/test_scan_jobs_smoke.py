# -*- coding: utf-8 -*-
"""扫描作业冒烟（P2b）：提交/轮询/失败/列表/裁剪。

用注入的假 runner 驱动作业状态，不依赖 OCR 真实环境；
路由层只验证 404 / 400 两条可离线路径。

运行：python test_scan_jobs_smoke.py
"""
import os
import sys
import tempfile
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "report_generator", "libs"))
sys.path.insert(0, os.path.join(ROOT, "report_generator"))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "webapp", "backend"))

import scan_jobs  # noqa: E402

from _harness import Results

_R = Results()
check = _R.check


skip = _R.skip


def _wait(job_id, timeout=5.0):
    deadline = time.time() + timeout
    view = scan_jobs.status(job_id)
    while time.time() < deadline:
        view = scan_jobs.status(job_id)
        if view and view.get("status") != "running":
            return view
        time.sleep(0.05)
    return view


def main():
    tmp = tempfile.mkdtemp(prefix="scan_jobs_")
    try:
        return _run(tmp)
    finally:
        import shutil
        shutil.rmtree(tmp, ignore_errors=True)


def _run(tmp):
    good = os.path.join(tmp, "good.png")
    with open(good, "wb") as fh:
        fh.write(b"\x89PNG\r\n\x1a\n")

    # 1. 成功作业
    def fake_ok(path, item):
        return {
            "doc_id": "doc-1", "detection_item": item or "回弹法检测",
            "sub_item": "梁", "columns": ["楼层", "构件编号"],
            "rows": [["1F", "L-1"]], "field_warnings": ["测区2 偏低"],
            "classification": {"item": "回弹法检测"}, "ocr_stats": {"pages": 1},
            "normalized": [{"巨": "大字段不应进作业"}],
        }

    submitted = scan_jobs.submit(good, "回弹法检测", runner=fake_ok)
    # 假 runner 可能在线程被调度前就跑完，两种状态都算正常
    check("提交返回作业视图", submitted["status"] in ("running", "done"),
          submitted["status"])
    check("提交带作业 id", submitted["id"].startswith("scan-"), submitted["id"])
    view = _wait(submitted["id"])
    check("作业完成", view and view["status"] == "done", view and view["status"])
    result = (view or {}).get("result") or {}
    check("结果保留 rows/columns",
          result.get("rows") == [["1F", "L-1"]]
          and result.get("columns") == ["楼层", "构件编号"], result.get("rows"))
    check("结果保留复核警告",
          result.get("field_warnings") == ["测区2 偏低"],
          result.get("field_warnings"))
    check("中间结构被裁剪",
          "normalized" not in result and "structured" not in result,
          sorted(result))
    check("完成时间与耗时已记录",
          bool(view.get("finished_at")) and view.get("duration_ms") >= 0,
          [view.get("finished_at"), view.get("duration_ms")])

    # 2. 失败作业
    def fake_fail(path, item):
        raise RuntimeError("OCR 引擎不可用")

    bad = scan_jobs.submit(good, None, runner=fake_fail)
    view = _wait(bad["id"])
    check("失败作业被记录", view and view["status"] == "failed",
          view and view["status"])
    check("失败原因可读", "OCR 引擎不可用" in (view.get("error") or ""),
          view.get("error"))
    check("失败作业无结果", view.get("result") is None, view.get("result"))

    # 3. 提交校验与查询
    try:
        scan_jobs.submit(os.path.join(tmp, "missing.png"))
        check("不存在的文件被拒", False, "未抛错")
    except scan_jobs.ScanJobError as e:
        check("不存在的文件被拒", "文件不存在" in str(e), str(e)[:80])

    check("未知作业返回 None", scan_jobs.status("scan-nope") is None)
    check("空 id 返回 None", scan_jobs.status("") is None)

    jobs = scan_jobs.list_jobs(limit=10)
    ids = [j["id"] for j in jobs]
    check("列表包含刚提交的作业", submitted["id"] in ids and bad["id"] in ids,
          ids[:3])
    check("列表默认不带结果",
          all("result" not in j for j in jobs), None)
    check("列表按最新优先", ids[0] == bad["id"], ids[:2])

    # 4. 作业数量裁剪（内存上限 50）
    for _ in range(scan_jobs._MAX_JOBS + 5):
        scan_jobs.submit(good, None, runner=lambda p, i: {})
    time.sleep(0.2)
    check("作业数量不超上限", len(scan_jobs._jobs) <= scan_jobs._MAX_JOBS,
          len(scan_jobs._jobs))
    check("列表长度受 limit 限制", len(scan_jobs.list_jobs(limit=5)) == 5,
          len(scan_jobs.list_jobs(limit=5)))

    # 5. 路由错误路径（不需要 OCR）
    try:
        import fastapi  # noqa: F401
    except ImportError:
        skip("路由错误路径", "当前解释器没有 fastapi")
        return _finish()

    from routers.scan import SubmitBody, scan_job, scan_submit
    try:
        scan_submit(SubmitBody(filepath=os.path.join("data", "uploads", "__missing_scan__.png")))
        check("路由拒绝缺失文件", False, "未抛错")
    except Exception as e:  # noqa: BLE001
        check("路由拒绝缺失文件", "文件不存在" in str(e), str(e)[:80])

    try:
        scan_job("scan-nope")
        check("路由返回 404", False, "未抛错")
    except Exception as e:  # noqa: BLE001
        status = getattr(e, "status_code", None)
        check("路由返回 404", status == 404, [status, str(e)[:60]])

    return _finish()


def _finish():
    return _R.finish()


if __name__ == "__main__":
    sys.exit(main())
