# -*- coding: utf-8 -*-
"""报告记录库 / 原始记录库路由。"""
from urllib.parse import quote

from fastapi import APIRouter
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from deps import ApiError, get_record_store, ok
from utils.record_search import rank_records
import record_reuse

router = APIRouter(tags=["records"])

# 结论补全的扫描上限：避免历史记录上万时逐条解压快照
MAX_CONCLUSION_SCAN = 100
MAX_SNAPSHOT_BYTES = 256 * 1024


@router.get("/records/stats")
def records_stats():
    try:
        return ok(get_record_store().stats(), "记录库统计读取成功")
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "data": None, "message": f"读取记录库统计失败：{e}"}


@router.get("/records/report")
def list_report_records(q: str = "", project: str = "",
                        limit: int = 50, offset: int = 0):
    try:
        items, total = get_record_store().list_report_records(
            q=q, project=project, limit=limit, offset=offset)
        return ok({"items": items, "total": total}, "报告记录读取成功")
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "data": None, "message": f"读取报告记录失败：{e}"}


@router.get("/records/original")
def list_original_records(q: str = "", project: str = "",
                          limit: int = 50, offset: int = 0):
    try:
        items, total = get_record_store().list_original_records(
            q=q, project=project, limit=limit, offset=offset)
        return ok({"items": items, "total": total}, "原始记录读取成功")
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "data": None, "message": f"读取原始记录失败：{e}"}


@router.get("/records/report/{record_id}")
def get_report_record(record_id: str):
    try:
        record = get_record_store().get_report_record(record_id)
        if not record:
            raise ApiError(f"报告记录不存在：{record_id}", 404)
        return ok(record, "报告记录详情读取成功")
    except ApiError:
        raise
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "data": None, "message": f"读取报告记录失败：{e}"}


@router.get("/records/original/{record_id}")
def get_original_record(record_id: str):
    try:
        record = get_record_store().get_original_record(record_id)
        if not record:
            raise ApiError(f"原始记录不存在：{record_id}", 404)
        return ok(record, "原始记录详情读取成功")
    except ApiError:
        raise
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "data": None, "message": f"读取原始记录失败：{e}"}


@router.get("/records/original/{record_id}/snapshot")
def get_original_snapshot(record_id: str):
    try:
        record = get_record_store().get_original_record(
            record_id, with_snapshot=True)
        if not record:
            raise ApiError(f"原始记录不存在：{record_id}", 404)
        if not record.get("has_snapshot"):
            raise ApiError("该原始记录没有数据快照", 404)
        snapshot = record.get("snapshot") or {}
        filename = (record.get("sheet_key") or "原始记录") + "_快照.json"
        return JSONResponse(
            content=snapshot,
            headers={"Content-Disposition":
                     "attachment; filename*=UTF-8''%s" % quote(filename)})
    except ApiError:
        raise
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "data": None, "message": f"读取原始记录快照失败：{e}"}


@router.delete("/records/report/{record_id}")
def delete_report_record(record_id: str):
    try:
        record = get_record_store().delete_report_record(record_id)
        if not record:
            raise ApiError(f"报告记录不存在：{record_id}", 404)
        return ok({"deleted": True, "filepath": record.get("filepath", "")},
                  "报告记录已删除（磁盘文件未删除）")
    except ApiError:
        raise
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "data": None, "message": f"删除报告记录失败：{e}"}


@router.delete("/records/original/{record_id}")
def delete_original_record(record_id: str):
    try:
        record = get_record_store().delete_original_record(record_id)
        if not record:
            raise ApiError(f"原始记录不存在：{record_id}", 404)
        return ok({"deleted": True, "filepath": record.get("filepath", "")},
                  "原始记录已删除（磁盘文件未删除）")
    except ApiError:
        raise
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "data": None, "message": f"删除原始记录失败：{e}"}


class ReuseBody(BaseModel):
    sheet_key: str = ""
    append: bool = False


def _original_items(store, project="", with_conclusion=True, limit=200):
    """原始记录列表；按需补上快照里的结论（有大小与条数上限）。"""
    rows, _total = store.list_original_records(q="", project=project,
                                               limit=limit, offset=0)
    items = []
    scanned = 0
    for row in rows:
        item = {
            "kind": "original",
            "id": row.get("id"),
            "project_name": row.get("project_name") or "",
            "sheet_key": row.get("sheet_key") or "",
            "base_item": row.get("base_item") or "",
            "template_name": row.get("template_name") or "",
            "filepath": row.get("filepath") or "",
            "filename": row.get("filename") or "",
            "generated_at": row.get("generated_at") or "",
            "rows": row.get("rows_count") or 0,
            "has_snapshot": bool(row.get("has_snapshot")),
            "exists": bool(row.get("exists")),
            "conclusion_type": "",
            "conclusion": "",
        }
        size = int(row.get("snapshot_size") or 0)
        if (with_conclusion and item["has_snapshot"]
                and scanned < MAX_CONCLUSION_SCAN
                and size <= MAX_SNAPSHOT_BYTES):
            scanned += 1
            try:
                record = store.get_original_record(item["id"],
                                                  with_snapshot=True)
                result = ((record or {}).get("snapshot") or {}).get(
                    "assessment_result") or {}
                item["conclusion_type"] = result.get("conclusion_type") or ""
                item["conclusion"] = result.get("conclusion") or ""
            except Exception:  # noqa: BLE001 - 单条快照坏了不影响检索
                pass
        items.append(item)
    return items


@router.get("/records/similar")
def similar_records(q: str = "", kind: str = "both", project: str = "",
                    limit: int = 10):
    """按项目名/检测项/模板/报告编号/结论检索历史记录，按相关度排序。"""
    try:
        kind = str(kind or "both").strip().lower()
        if kind not in ("both", "report", "original"):
            raise ApiError("kind 只支持 both / report / original")
        store = get_record_store()
        items = []
        if kind in ("both", "report"):
            rows, _total = store.list_report_records(q="", project=project,
                                                     limit=200, offset=0)
            for row in rows:
                items.append({
                    "kind": "report",
                    "id": row.get("id"),
                    "project_name": row.get("project_name") or "",
                    "sheet_key": "",
                    "base_item": "",
                    "report_no": row.get("report_no") or "",
                    "template_name": row.get("template_name") or "",
                    "filepath": row.get("filepath") or "",
                    "filename": row.get("filename") or "",
                    "generated_at": row.get("generated_at") or "",
                    "rows": row.get("tables") or 0,
                    "has_snapshot": False,
                    "exists": bool(row.get("exists")),
                })
        if kind in ("both", "original"):
            items.extend(_original_items(store, project=project))
        ranked = rank_records(items, q, limit=limit)
        return ok({"items": ranked, "count": len(ranked), "query": q,
                   "kind": kind}, "历史记录检索完成：%d 条" % len(ranked))
    except ApiError:
        raise
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "data": None, "message": f"检索历史记录失败：{e}"}


@router.get("/records/original/{record_id}/sheets")
def original_record_sheets(record_id: str):
    """列出该原始记录快照里可复用的数据表（含与当前列定义的兼容性）。"""
    try:
        return ok(record_reuse.list_record_sheets(record_id),
                  "原始记录快照读取成功")
    except record_reuse.ReuseError as e:
        raise ApiError(str(e), 404)
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "data": None, "message": f"读取快照数据表失败：{e}"}


@router.post("/records/original/{record_id}/reuse")
def reuse_original_record(record_id: str, body: ReuseBody):
    """把历史原始记录快照里的表复制到当前工程（默认覆盖，append=true 追加）。"""
    try:
        result = record_reuse.reuse_record(record_id,
                                           sheet_key=body.sheet_key or None,
                                           append=body.append)
        return ok(result, "已复用历史数据：%s（%d 行）"
                  % (result["sheet_key"], result["rows"]))
    except record_reuse.ReuseError as e:
        raise ApiError(str(e))
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "data": None, "message": f"复用历史数据失败：{e}"}


@router.post("/records/import_legacy")
def import_legacy_records():
    try:
        store = get_record_store()
        store.import_legacy()
        return ok(store.stats(), "历史记录已重新导入")
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "data": None, "message": f"导入历史记录失败：{e}"}
