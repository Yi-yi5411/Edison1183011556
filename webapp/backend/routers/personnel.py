# -*- coding: utf-8 -*-
"""人员库路由：人员信息 CRUD 与 Excel 导入。"""
import os
import tempfile

from fastapi import APIRouter, File, UploadFile
from pydantic import BaseModel

from deps import ApiError, ok
from utils import personnel_store
from utils.excel_import import ExcelImportError, read_rows

router = APIRouter(tags=["personnel"])

_IMPORT_ALIASES = {
    "name": ("姓名", "名字", "人员姓名", "检测人员"),
    "role": ("岗位", "角色", "职务", "岗位名称", "人员岗位"),
    "cert_no": ("证书编号", "证书号", "资格证号", "上岗证号", "岗位证书编号"),
    "phone": ("电话", "手机", "手机号", "联系电话", "联系方式"),
    "organization": ("单位", "所属单位", "工作单位", "公司", "检测单位"),
    "note": ("备注", "说明"),
    "active": ("状态", "启用", "是否启用", "在职"),
}


def _norm_header(value):
    text = str(value or "").strip().replace(" ", "").replace("　", "")
    return text.replace("(", "（").replace(")", "）")


def _header_index(headers):
    """按表头名称找字段列；返回 {字段: 列索引} 和已匹配字段数。"""
    mapping = {}
    for i, header in enumerate(headers):
        text = _norm_header(header)
        if not text:
            continue
        for key, aliases in _IMPORT_ALIASES.items():
            if key in mapping:
                continue
            for alias in aliases:
                if text == alias or text.startswith(alias):
                    mapping[key] = i
                    break
    return mapping


def _truthy(value):
    text = str(value or "").strip().lower()
    if text in ("", "1", "是", "启用", "在职", "true", "yes", "y"):
        return True
    if text in ("0", "否", "停用", "离职", "false", "no", "n"):
        return False
    return True


@router.post("/personnel/import")
async def import_personnel(file: UploadFile = File(...)):
    """从 Excel/CSV/Word 表格导入人员；按表头识别姓名、岗位等列。"""
    tmp_dir = tempfile.mkdtemp(prefix="personnel_import_")
    try:
        name = os.path.basename(file.filename or "personnel.xlsx")
        if not name.lower().endswith((".xlsx", ".xlsm", ".csv", ".docx")):
            raise ApiError("仅支持 .xlsx / .xlsm / .csv / .docx 文件")
        path = os.path.join(tmp_dir, name)
        with open(path, "wb") as out:
            out.write(await file.read())
        rows = read_rows(path)
        if not rows:
            raise ApiError("文件为空")
        header_idx = None
        header_map = {}
        for i, row in enumerate(rows[:15]):
            found = _header_index(row)
            if len(found) >= 2 and (header_idx is None or len(found) > len(header_map)):
                header_idx = i
                header_map = found
        if header_idx is None or "name" not in header_map:
            raise ApiError("未找到人员表头，请至少包含“姓名”列")
        items = []
        warnings = []
        for row_no, row in enumerate(rows[header_idx + 1:], start=header_idx + 2):
            if not any(str(v).strip() for v in row):
                continue
            def get(key):
                idx = header_map.get(key)
                return row[idx] if idx is not None and idx < len(row) else ""
            person = {
                "name": str(get("name") or "").strip(),
                "role": str(get("role") or "").strip(),
                "cert_no": str(get("cert_no") or "").strip(),
                "phone": str(get("phone") or "").strip(),
                "organization": str(get("organization") or "").strip(),
                "note": str(get("note") or "").strip(),
                "active": _truthy(get("active")),
            }
            if not person["name"]:
                warnings.append("第 %d 行姓名为空，已跳过" % row_no)
                continue
            items.append(person)
        if not items:
            raise ApiError("文件中没有可导入的人员数据")
        result = personnel_store.import_personnel(items)
        return ok({
            "created": result["created"],
            "updated": result["updated"],
            "skipped": result["skipped"],
            "total": result["total"],
            "warnings": warnings,
        }, f"已导入 {result['created']} 人，更新 {result['updated']} 人")
    except ApiError:
        raise
    except ExcelImportError as e:
        raise ApiError(str(e))
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "data": None, "message": f"导入人员失败：{e}"}
    finally:
        import shutil
        shutil.rmtree(tmp_dir, ignore_errors=True)


class PersonnelBody(BaseModel):
    name: str = ""
    role: str = ""
    cert_no: str = ""
    phone: str = ""
    organization: str = ""
    note: str = ""
    active: bool = True


@router.get("/personnel")
def list_personnel(q: str = "", role: str = "", active_only: bool = False,
                   limit: int = 200, offset: int = 0):
    try:
        return ok(personnel_store.list_personnel(
            query=q, role=role, active_only=active_only,
            limit=limit, offset=offset), "人员库读取成功")
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "data": None, "message": f"读取人员库失败：{e}"}


@router.get("/personnel/status")
def personnel_status():
    try:
        return ok(personnel_store.status(), "人员库状态读取成功")
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "data": None, "message": f"读取人员库状态失败：{e}"}


@router.get("/personnel/{person_id}")
def get_personnel(person_id: str):
    item = personnel_store.get_personnel(person_id)
    if not item:
        raise ApiError("人员不存在", 404)
    return ok(item, "人员信息读取成功")


@router.post("/personnel")
def create_personnel(body: PersonnelBody):
    try:
        return ok(personnel_store.create_personnel(body.model_dump()), "人员已新增")
    except ValueError as e:
        raise ApiError(str(e))
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "data": None, "message": f"新增人员失败：{e}"}


@router.put("/personnel/{person_id}")
def update_personnel(person_id: str, body: PersonnelBody):
    try:
        item = personnel_store.update_personnel(person_id, body.model_dump())
        if not item:
            raise ApiError("人员不存在", 404)
        return ok(item, "人员信息已保存")
    except ApiError:
        raise
    except ValueError as e:
        raise ApiError(str(e))
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "data": None, "message": f"保存人员失败：{e}"}


@router.delete("/personnel/{person_id}")
def delete_personnel(person_id: str):
    try:
        if not personnel_store.delete_personnel(person_id):
            raise ApiError("人员不存在", 404)
        return ok({"id": person_id}, "人员已删除")
    except ApiError:
        raise
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "data": None, "message": f"删除人员失败：{e}"}
