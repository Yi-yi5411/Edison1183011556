# -*- coding: utf-8 -*-
"""报告 / 原始记录模板库（SQLite 持久化，无 Qt / FastAPI 依赖）。

职责：
  - 建库/内置种子（报告模板 1 个，原始记录原生模板 10 个）
  - 报告模板包（ZIP + manifest）导入/导出/设默认/删除
  - 原始记录 .docx/.doc 导入、设默认、下载、预览
  - 按检测项目解析默认原始记录模板
"""
import json
import os
import shutil
import sqlite3
import threading
import uuid
from datetime import datetime
from pathlib import Path

try:
    from report_generator.framework.resources import PROJECT_ROOT
    from report_generator.utils.original_record import generate_native_record
    from report_generator.utils.original_record_fill import (
        fill_imported_record,
        inspect_docx,
    )
    from report_generator.utils.original_record_templates import (
        BUILTIN_ORIGINAL_TEMPLATES,
        get_builtin_definition,
        match_builtin_template,
    )
    from report_generator.utils.report_templates import (
        ReportTemplateSet,
        build_builtin_manifest,
    )
    from report_generator.utils.template_package import (
        TemplatePackageError,
        export_report_package,
        load_report_package,
    )
except ImportError:  # 以 report_generator/ 为工作目录导入时
    from framework.resources import PROJECT_ROOT
    from utils.original_record import generate_native_record
    from utils.original_record_fill import fill_imported_record, inspect_docx
    from utils.original_record_templates import (
        BUILTIN_ORIGINAL_TEMPLATES,
        get_builtin_definition,
        match_builtin_template,
    )
    from utils.report_templates import (
        ReportTemplateSet,
        build_builtin_manifest,
    )
    from utils.template_package import (
        TemplatePackageError,
        export_report_package,
        load_report_package,
    )


SEED_VERSION = 2  # v2：刷新内置报告模板的结果表列别名
BUILTIN_REPORT_ID = "builtin_standard"
BUILTIN_REPORT_ROOT = "report_template"


class TemplateError(Exception):
    """模板库业务异常（中文消息）。"""


def _now():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _json_dumps(value):
    return json.dumps(value, ensure_ascii=False)


def _json_loads(text, default):
    try:
        data = json.loads(text or "")
        return data if data is not None else default
    except Exception:  # noqa: BLE001
        return default


class TemplateLibrary(object):
    """线程安全的模板库。"""

    def __init__(self, root=None, db_path=None):
        self.root = Path(root).resolve() if root else Path(PROJECT_ROOT).resolve()
        self.data_dir = self.root / "data"
        self.report_import_dir = self.data_dir / "templates" / "report"
        self.original_import_dir = self.data_dir / "templates" / "original"
        self.tmp_dir = self.data_dir / "templates" / "_tmp"
        for p in (self.data_dir, self.report_import_dir,
                  self.original_import_dir, self.tmp_dir):
            p.mkdir(parents=True, exist_ok=True)
        self.db_path = Path(db_path).resolve() if db_path else (
            self.data_dir / "template_library.db")
        self._lock = threading.RLock()
        self._conn = sqlite3.connect(str(self.db_path), check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._init_schema()
        self._seed()

    # ── 基础 ──
    def close(self):
        with self._lock:
            self._conn.close()

    def _init_schema(self):
        with self._lock, self._conn:
            self._conn.execute("""
                CREATE TABLE IF NOT EXISTS report_templates (
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    description TEXT,
                    root_dir TEXT NOT NULL,
                    manifest_json TEXT NOT NULL,
                    builtin INTEGER DEFAULT 0,
                    is_default INTEGER DEFAULT 0,
                    created_at TEXT,
                    updated_at TEXT
                )
            """)
            self._conn.execute("""
                CREATE TABLE IF NOT EXISTS original_templates (
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    code TEXT,
                    detection_items TEXT,
                    engine TEXT,
                    file_path TEXT,
                    config_json TEXT,
                    reference_doc TEXT,
                    builtin INTEGER DEFAULT 0,
                    created_at TEXT,
                    updated_at TEXT
                )
            """)
            self._conn.execute("""
                CREATE TABLE IF NOT EXISTS original_defaults (
                    item TEXT PRIMARY KEY,
                    template_id TEXT NOT NULL
                )
            """)
            self._conn.execute("""
                CREATE TABLE IF NOT EXISTS meta (
                    key TEXT PRIMARY KEY,
                    value TEXT
                )
            """)

    def _meta_get(self, key, default=""):
        with self._lock:
            row = self._conn.execute(
                "SELECT value FROM meta WHERE key=?", (key,)).fetchone()
        return row["value"] if row else default

    def _meta_set(self, key, value):
        with self._lock, self._conn:
            self._conn.execute(
                "INSERT OR REPLACE INTO meta(key, value) VALUES(?,?)",
                (key, str(value)))

    def _resolve(self, rel):
        if not rel:
            return None
        p = Path(str(rel))
        if p.is_absolute():
            return str(p)
        return str((self.root / p).resolve())

    def _to_rel(self, path):
        try:
            return os.path.relpath(str(path), str(self.root)).replace("\\", "/")
        except ValueError:
            return str(path)

    def _delete_tree(self, path, base):
        path = Path(path).resolve()
        base = Path(base).resolve()
        try:
            if path == base or base not in path.parents:
                return
        except Exception:  # noqa: BLE001
            return
        if path.exists():
            shutil.rmtree(str(path), ignore_errors=True)

    # ── 内置种子 ──
    def _seed(self):
        version = int(self._meta_get("seed_version", "0") or 0)
        need = version < SEED_VERSION
        self._seed_report(need)
        self._seed_original(need)
        if need:
            self._meta_set("seed_version", SEED_VERSION)

    def _seed_report(self, need):
        manifest = build_builtin_manifest()
        existing = self._get_report_row(BUILTIN_REPORT_ID)
        now = _now()
        if existing is None:
            default = self._default_report_row()
            is_default = 1 if default is None else 0
            with self._lock, self._conn:
                self._conn.execute(
                    """INSERT INTO report_templates
                       (id,name,description,root_dir,manifest_json,builtin,
                        is_default,created_at,updated_at)
                       VALUES(?,?,?,?,?,?,?,?,?)""",
                    (BUILTIN_REPORT_ID, manifest.get("name") or "标准检测报告模板",
                     manifest.get("description") or "", BUILTIN_REPORT_ROOT,
                     _json_dumps(manifest), 1, is_default, now, now))
            return
        if need:
            with self._lock, self._conn:
                self._conn.execute(
                    """UPDATE report_templates
                       SET name=?, description=?, root_dir=?, manifest_json=?,
                           updated_at=? WHERE id=?""",
                    (manifest.get("name") or existing["name"],
                     manifest.get("description") or "",
                     BUILTIN_REPORT_ROOT, _json_dumps(manifest), now,
                     BUILTIN_REPORT_ID))
            if self._default_report_row() is None:
                self.set_default_report_template(BUILTIN_REPORT_ID)

    def _seed_original(self, need):
        now = _now()
        for definition in BUILTIN_ORIGINAL_TEMPLATES:
            template_id = definition.get("id")
            if not template_id:
                continue
            existing = self._get_original_row(template_id)
            ref = str(definition.get("reference_doc") or "")
            if ref and not (self.root / Path(ref)).is_file():
                # 参考文件缺失时仍保留路径，下载接口会给出中文提示
                pass
            config_json = _json_dumps(definition)
            items_json = _json_dumps(definition.get("detection_items") or [])
            if existing is None:
                with self._lock, self._conn:
                    self._conn.execute(
                        """INSERT INTO original_templates
                           (id,name,code,detection_items,engine,file_path,
                            config_json,reference_doc,builtin,created_at,updated_at)
                           VALUES(?,?,?,?,?,?,?,?,?,?,?)""",
                        (template_id, definition.get("name") or template_id,
                         definition.get("code") or "", items_json,
                         "native_docx", "", config_json, ref, 1, now, now))
            elif need:
                with self._lock, self._conn:
                    self._conn.execute(
                        """UPDATE original_templates
                           SET name=?, code=?, detection_items=?, engine=?,
                               config_json=?, reference_doc=?, updated_at=?
                           WHERE id=?""",
                        (definition.get("name") or template_id,
                         definition.get("code") or "", items_json,
                         "native_docx", config_json, ref, now, template_id))
        # 逐检测项默认（已存在默认则保留）
        with self._lock, self._conn:
            for definition in BUILTIN_ORIGINAL_TEMPLATES:
                for item in definition.get("detection_items") or []:
                    self._conn.execute(
                        "INSERT OR IGNORE INTO original_defaults(item, template_id) "
                        "VALUES(?,?)", (item, definition["id"]))

    # ── 报告模板 ──
    def _get_report_row(self, template_id):
        with self._lock:
            row = self._conn.execute(
                "SELECT * FROM report_templates WHERE id=?",
                (template_id,)).fetchone()
        return dict(row) if row else None

    def _default_report_row(self):
        with self._lock:
            row = self._conn.execute(
                "SELECT * FROM report_templates WHERE is_default=1 "
                "ORDER BY updated_at DESC LIMIT 1").fetchone()
        return dict(row) if row else None

    def _report_set(self, row):
        manifest = _json_loads(row.get("manifest_json"), {})
        root = self._resolve(row.get("root_dir"))
        ts = ReportTemplateSet.from_manifest(
            root, manifest, template_id=row.get("id"),
            name=row.get("name") or "")
        return ts

    def _report_view(self, row):
        ts = self._report_set(row)
        missing = ts.missing_files()
        return {
            "id": row.get("id"),
            "name": row.get("name"),
            "description": row.get("description") or "",
            "builtin": bool(row.get("builtin")),
            "is_default": bool(row.get("is_default")),
            "available": not missing,
            "missing": missing[:20],
            "chapter_count": len(ts.chapters),
            "table_count": len(ts.result_tables),
            "created_at": row.get("created_at") or "",
            "updated_at": row.get("updated_at") or "",
        }

    def list_report_templates(self):
        with self._lock:
            rows = self._conn.execute(
                "SELECT * FROM report_templates ORDER BY builtin DESC, id").fetchall()
        return [self._report_view(dict(r)) for r in rows]

    def default_report_template_id(self):
        row = self._default_report_row()
        if row:
            return row.get("id")
        rows = self.list_report_templates()
        return rows[0]["id"] if rows else ""

    def get_report_template_set(self, template_id=None):
        row = self._get_report_row(template_id) if template_id else None
        if row is None:
            row = self._default_report_row()
        if row is None:
            return ReportTemplateSet.builtin()
        return self._report_set(row)

    def get_report_template(self, template_id):
        row = self._get_report_row(template_id)
        if not row:
            return None
        view = self._report_view(row)
        view["manifest"] = _json_loads(row.get("manifest_json"), {})
        return view

    def set_default_report_template(self, template_id):
        row = self._get_report_row(template_id)
        if not row:
            raise TemplateError("报告模板不存在：%s" % template_id)
        view = self._report_view(row)
        if not view["available"]:
            raise TemplateError("报告模板文件缺失，不能设为默认：%s" % template_id)
        with self._lock, self._conn:
            self._conn.execute("UPDATE report_templates SET is_default=0")
            self._conn.execute(
                "UPDATE report_templates SET is_default=1, updated_at=? WHERE id=?",
                (_now(), template_id))
        return self._report_view(self._get_report_row(template_id))

    def import_report_package(self, zip_path):
        work = self.tmp_dir / ("report_" + uuid.uuid4().hex[:12])
        work.mkdir(parents=True, exist_ok=True)
        try:
            package_root, manifest, warnings = load_report_package(zip_path, work)
            template_id = "report_" + uuid.uuid4().hex[:10]
            target = self.report_import_dir / template_id
            shutil.copytree(package_root, str(target))
            root_rel = self._to_rel(target)
            now = _now()
            with self._lock, self._conn:
                self._conn.execute(
                    """INSERT INTO report_templates
                       (id,name,description,root_dir,manifest_json,builtin,
                        is_default,created_at,updated_at)
                       VALUES(?,?,?,?,?,?,?,?,?)""",
                    (template_id,
                     manifest.get("name") or Path(zip_path).stem,
                     manifest.get("description") or "", root_rel,
                     _json_dumps(manifest), 0, 0, now, now))
            return self._report_view(self._get_report_row(template_id)), warnings
        except TemplatePackageError:
            raise
        except Exception as e:  # noqa: BLE001
            raise TemplateError("导入报告模板失败：%s" % e)
        finally:
            shutil.rmtree(str(work), ignore_errors=True)

    def delete_report_template(self, template_id):
        row = self._get_report_row(template_id)
        if not row:
            raise TemplateError("报告模板不存在：%s" % template_id)
        if row.get("builtin"):
            raise TemplateError("内置报告模板不可删除")
        if row.get("is_default"):
            raise TemplateError("该模板正在作为默认模板，请先设置其他模板为默认")
        with self._lock, self._conn:
            self._conn.execute("DELETE FROM report_templates WHERE id=?",
                               (template_id,))
        root = self._resolve(row.get("root_dir"))
        if root:
            self._delete_tree(root, self.report_import_dir)
        return True

    def export_report_template(self, template_id, output_zip=None):
        row = self._get_report_row(template_id)
        if not row:
            raise TemplateError("报告模板不存在：%s" % template_id)
        manifest = _json_loads(row.get("manifest_json"), {})
        root = self._resolve(row.get("root_dir"))
        if not os.path.isdir(root):
            raise TemplateError("报告模板目录不存在：%s" % root)
        if not output_zip:
            output_zip = str(self.tmp_dir / ("%s_%s.zip" % (
                template_id, datetime.now().strftime("%Y%m%d_%H%M%S"))))
        return export_report_package(root, manifest, output_zip)

    # ── 原始记录模板 ──
    def _get_original_row(self, template_id):
        with self._lock:
            row = self._conn.execute(
                "SELECT * FROM original_templates WHERE id=?",
                (template_id,)).fetchone()
        return dict(row) if row else None

    def _defaults_for(self, template_id):
        with self._lock:
            rows = self._conn.execute(
                "SELECT item FROM original_defaults WHERE template_id=? "
                "ORDER BY item", (template_id,)).fetchall()
        return [r["item"] for r in rows]

    def _original_view(self, row):
        engine = row.get("engine") or "native_docx"
        file_path = row.get("file_path") or ""
        if engine == "native_docx":
            available = True
        else:
            available = bool(file_path and os.path.isfile(
                self._resolve(file_path) or ""))
        ref = row.get("reference_doc") or ""
        return {
            "id": row.get("id"),
            "name": row.get("name"),
            "code": row.get("code") or "",
            "engine": engine,
            "fillable": engine in ("native_docx", "docx_import"),
            "available": available,
            "builtin": bool(row.get("builtin")),
            "detection_items": _json_loads(row.get("detection_items"), []),
            "default_for": self._defaults_for(row.get("id")),
            "reference_doc": ref,
            "reference_available": bool(ref and os.path.isfile(
                self._resolve(ref) or "")),
            "config": _json_loads(row.get("config_json"), {}),
            "created_at": row.get("created_at") or "",
            "updated_at": row.get("updated_at") or "",
        }

    def list_original_templates(self):
        with self._lock:
            rows = self._conn.execute(
                "SELECT * FROM original_templates ORDER BY builtin DESC, id").fetchall()
        return [self._original_view(dict(r)) for r in rows]

    def get_original_template(self, template_id):
        row = self._get_original_row(template_id)
        return self._original_view(row) if row else None

    def defaults_map(self):
        with self._lock:
            rows = self._conn.execute(
                "SELECT item, template_id FROM original_defaults").fetchall()
        return {r["item"]: r["template_id"] for r in rows}

    def default_template_id_for_item(self, base_item):
        base = str(base_item or "").strip()
        if base:
            with self._lock:
                row = self._conn.execute(
                    "SELECT template_id FROM original_defaults WHERE item=?",
                    (base,)).fetchone()
            if row:
                return row["template_id"]
        matched = match_builtin_template(base)
        return matched.get("id") if matched else "builtin_generic"

    def resolve_original_template(self, base_item, template_id=None):
        """解析检测项应使用的原始记录模板；返回 view 或 None。"""
        if template_id:
            view = self.get_original_template(template_id)
            if view:
                return view
        default_id = self.default_template_id_for_item(base_item)
        view = self.get_original_template(default_id)
        if view:
            return view
        matched = match_builtin_template(base_item)
        if matched:
            return self.get_original_template(matched.get("id"))
        return self.get_original_template("builtin_generic")

    def import_original_template(self, file_path, name, code="",
                                 detection_items=None, set_default=False):
        """导入 .docx/.doc 原始记录模板。"""
        file_path = os.path.abspath(str(file_path or ""))
        if not os.path.isfile(file_path):
            raise TemplateError("上传文件不存在：%s" % file_path)
        suffix = os.path.splitext(file_path)[1].lower()
        if suffix not in (".docx", ".doc"):
            raise TemplateError("仅支持 .docx / .doc 原始记录模板")
        if os.path.getsize(file_path) > 100 * 1024 * 1024:
            raise TemplateError("模板文件超过 100MB，已拒绝导入")
        name = str(name or "").strip() or Path(file_path).stem
        template_id = "original_" + uuid.uuid4().hex[:10]
        target_dir = self.original_import_dir / template_id
        target_dir.mkdir(parents=True, exist_ok=True)
        try:
            if suffix == ".docx":
                target = target_dir / "template.docx"
                shutil.copy2(file_path, target)
                try:
                    from docx import Document
                    Document(str(target))
                except Exception as e:  # noqa: BLE001
                    raise TemplateError("上传文件不是有效的 .docx：%s" % e)
                engine = "docx_import"
                config = {"source_name": os.path.basename(file_path)}
            else:
                target = target_dir / "template.doc"
                shutil.copy2(file_path, target)
                with open(str(target), "rb") as f:
                    magic = f.read(8)
                if magic != b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1":
                    raise TemplateError("上传文件不是有效的 .doc 文件")
                engine = "doc_archive"
                config = {"source_name": os.path.basename(file_path)}
            items = []
            for item in detection_items or []:
                item = str(item or "").strip()
                if item and item not in items:
                    items.append(item)
            now = _now()
            with self._lock, self._conn:
                self._conn.execute(
                    """INSERT INTO original_templates
                       (id,name,code,detection_items,engine,file_path,
                        config_json,reference_doc,builtin,created_at,updated_at)
                       VALUES(?,?,?,?,?,?,?,?,?,?,?)""",
                    (template_id, name, str(code or ""), _json_dumps(items),
                     engine, self._to_rel(target), _json_dumps(config), "",
                     0, now, now))
            if set_default and engine in ("native_docx", "docx_import"):
                self.set_original_defaults(template_id, items)
            return self.get_original_template(template_id)
        except TemplateError:
            shutil.rmtree(str(target_dir), ignore_errors=True)
            raise
        except Exception as e:  # noqa: BLE001
            shutil.rmtree(str(target_dir), ignore_errors=True)
            raise TemplateError("导入原始记录模板失败：%s" % e)

    def set_original_defaults(self, template_id, items):
        view = self.get_original_template(template_id)
        if not view:
            raise TemplateError("原始记录模板不存在：%s" % template_id)
        if not view["fillable"]:
            raise TemplateError(".doc 存档模板不支持自动填充，不能设为默认")
        cleaned = []
        for item in items or []:
            item = str(item or "").strip()
            if item and item not in cleaned:
                cleaned.append(item)
        with self._lock, self._conn:
            self._conn.execute(
                "DELETE FROM original_defaults WHERE template_id=?",
                (template_id,))
            for item in cleaned:
                self._conn.execute(
                    "INSERT OR REPLACE INTO original_defaults(item, template_id) "
                    "VALUES(?,?)", (item, template_id))
        return self.get_original_template(template_id)

    def delete_original_template(self, template_id):
        row = self._get_original_row(template_id)
        if not row:
            raise TemplateError("原始记录模板不存在：%s" % template_id)
        if row.get("builtin"):
            raise TemplateError("内置原始记录模板不可删除")
        if self._defaults_for(template_id):
            raise TemplateError("该模板正在作为默认模板，请先设置其他模板为默认")
        with self._lock, self._conn:
            self._conn.execute("DELETE FROM original_templates WHERE id=?",
                               (template_id,))
        file_path = self._resolve(row.get("file_path"))
        if file_path:
            parent = Path(file_path).parent
            self._delete_tree(parent, self.original_import_dir)
        return True

    def get_original_file_path(self, template_id):
        row = self._get_original_row(template_id)
        if not row:
            raise TemplateError("原始记录模板不存在：%s" % template_id)
        if row.get("engine") == "native_docx":
            return ""
        path = self._resolve(row.get("file_path"))
        if not path or not os.path.isfile(path):
            raise TemplateError("原始记录模板文件不存在：%s" % (row.get("file_path") or ""))
        return path

    def reference_doc_path(self, template_id):
        row = self._get_original_row(template_id)
        if not row:
            raise TemplateError("原始记录模板不存在：%s" % template_id)
        ref = row.get("reference_doc") or ""
        path = self._resolve(ref)
        if not path or not os.path.isfile(path):
            raise TemplateError("官方参考模板不存在：%s" % (ref or "未配置"))
        return path

    def preview_original_template(self, template_id):
        view = self.get_original_template(template_id)
        if not view:
            raise TemplateError("原始记录模板不存在：%s" % template_id)
        engine = view["engine"]
        if engine == "native_docx":
            config = view.get("config") or {}
            return {
                "kind": "native",
                "name": view["name"],
                "code": view["code"],
                "detection_items": view["detection_items"],
                "columns": config.get("columns", "all"),
                "orientation": config.get("orientation", "auto"),
                "notes": config.get("notes", ""),
            }
        if engine == "docx_import":
            path = self.get_original_file_path(template_id)
            data = inspect_docx(path)
            data["kind"] = "docx"
            data["name"] = view["name"]
            return data
        return {
            "kind": "archive",
            "name": view["name"],
            "message": ".doc 存档模板不支持自动填充，请在 WPS/Word 中另存为 .docx 后重新上传",
        }

    def blank_original_template(self, template_id, columns=None, info=None):
        """生成/返回空白原始记录模板，返回 (path, warnings)。"""
        view = self.get_original_template(template_id)
        if not view:
            raise TemplateError("原始记录模板不存在：%s" % template_id)
        if view["engine"] == "native_docx":
            definition = view.get("config") or get_builtin_definition(template_id) or {}
            cols = list(columns or [])
            output = self.tmp_dir / ("blank_%s_%s.docx" % (
                template_id, datetime.now().strftime("%Y%m%d_%H%M%S")))
            return generate_native_record(
                definition, view["name"], cols, [], dict(info or {}),
                output_path=str(output), blank=True)
        path = self.get_original_file_path(template_id)
        return path, []
