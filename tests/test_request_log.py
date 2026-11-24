# -*- coding: utf-8 -*-
"""P8 访问日志冒烟：结构化字段、轮转、关闭开关、X-Request-ID 透传。

运行：python test_request_log.py
"""
import json
import os
import shutil
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "report_generator", "libs"))
sys.path.insert(0, os.path.join(ROOT, "report_generator"))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "webapp", "backend"))

import request_log  # noqa: E402

from _harness import Results

_R = Results()
check = _R.check


skip = _R.skip


def _read(path):
    with open(path, "r", encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def test_fields():
    tmp = tempfile.mkdtemp(prefix="log_")
    old = os.environ.get("STRUCTURAL_LOG_DIR")
    os.environ["STRUCTURAL_LOG_DIR"] = tmp
    try:
        entry = request_log.log_request(
            "get", "/api/project", 200, 12.7, request_id="abc123",
            client="127.0.0.1", query_keys=["b", "a", "b"],
            project_name="测试工程")
        check("返回日志条目", isinstance(entry, dict), entry)
        check("请求 ID 保留", entry["request_id"] == "abc123", entry["request_id"])
        check("方法大写", entry["method"] == "GET", entry["method"])
        check("耗时取整", entry["duration_ms"] == 12, entry["duration_ms"])
        check("查询参数名去重排序", entry["query_keys"] == ["a", "b"],
              entry["query_keys"])
        check("带工程名", entry["project"] == "测试工程", entry["project"])

        entries = _read(request_log.log_file())
        check("落盘一行", len(entries) == 1, len(entries))
        check("不记录查询值", "secret" not in json.dumps(entries,
                                                   ensure_ascii=False))
    finally:
        if old is None:
            os.environ.pop("STRUCTURAL_LOG_DIR", None)
        else:
            os.environ["STRUCTURAL_LOG_DIR"] = old
        shutil.rmtree(tmp, ignore_errors=True)


def test_rotate_and_disable():
    tmp = tempfile.mkdtemp(prefix="log_")
    old_dir = os.environ.get("STRUCTURAL_LOG_DIR")
    old_max = request_log.MAX_BYTES
    os.environ["STRUCTURAL_LOG_DIR"] = tmp
    request_log.MAX_BYTES = 120
    try:
        for index in range(4):
            request_log.log_request("GET", "/api/x", 200, 1,
                                    request_id="r%d" % index)
        check("超限轮转为 .1", os.path.isfile(request_log.log_file() + ".1"))
        check("当前文件仍有内容", os.path.getsize(request_log.log_file()) > 0)

        os.environ["STRUCTURAL_ACCESS_LOG"] = "off"
        before = os.path.getsize(request_log.log_file())
        request_log.log_request("GET", "/api/y", 200, 1)
        check("关闭后不再写", os.path.getsize(request_log.log_file()) == before)
        os.environ.pop("STRUCTURAL_ACCESS_LOG", None)
    finally:
        request_log.MAX_BYTES = old_max
        if old_dir is None:
            os.environ.pop("STRUCTURAL_LOG_DIR", None)
        else:
            os.environ["STRUCTURAL_LOG_DIR"] = old_dir
        shutil.rmtree(tmp, ignore_errors=True)


def test_middleware():
    try:
        import fastapi  # noqa: F401
        from fastapi.testclient import TestClient  # noqa: F401
    except ImportError:
        skip("中间件", "当前解释器没有 fastapi/httpx")
        return
    tmp = tempfile.mkdtemp(prefix="log_")
    old = os.environ.get("STRUCTURAL_LOG_DIR")
    os.environ["STRUCTURAL_LOG_DIR"] = tmp
    try:
        import main
        client = TestClient(main.app)
        resp = client.get("/api/health")
        check("健康检查 200", resp.status_code == 200, resp.status_code)
        rid = resp.headers.get("X-Request-ID")
        check("响应带 X-Request-ID", bool(rid), rid)

        resp2 = client.get("/api/health", headers={"X-Request-ID": "upstream1"})
        check("上游 ID 透传", resp2.headers.get("X-Request-ID") == "upstream1",
              resp2.headers.get("X-Request-ID"))

        client.get("/api/project?api_key=secret-value")
        entries = _read(request_log.log_file())
        check("中间件写入日志", len(entries) >= 2, len(entries))
        health = [e for e in entries if e["path"] == "/api/health"]
        check("日志含状态与耗时",
              health and health[0]["status"] == 200
              and isinstance(health[0]["duration_ms"], int),
              health[0] if health else None)
        check("日志不含查询值",
              "secret-value" not in json.dumps(entries, ensure_ascii=False))
        check("带工程名", bool(health[0].get("project")), health[0].get("project"))
    except Exception as exc:  # noqa: BLE001
        check("中间件可用", False, str(exc)[:120])
    finally:
        if old is None:
            os.environ.pop("STRUCTURAL_LOG_DIR", None)
        else:
            os.environ["STRUCTURAL_LOG_DIR"] = old
        shutil.rmtree(tmp, ignore_errors=True)


def main():
    test_fields()
    test_rotate_and_disable()
    test_middleware()
    return _R.finish()


if __name__ == "__main__":
    sys.exit(main())
