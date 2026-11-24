# -*- coding: utf-8 -*-
"""报告模板包（ZIP + manifest.json）的导入/导出辅助（无 Qt 依赖）。

导入流程：
  1. 安全解压（禁止绝对路径、..、超大文件、非 docx/json 文件）；
  2. 定位 manifest.json（支持 ZIP 内多一层目录）；
  3. 校验 8 个章节与结果表文件存在且为有效 .docx；
  4. 调用方把 package_root 复制到模板库目录。
"""
import json
import os
import zipfile

from docx import Document

try:
    from report_generator.utils.report_templates import (
        REQUIRED_CHAPTERS,
        validate_manifest,
    )
except ImportError:  # 以 report_generator/ 为工作目录导入时
    from utils.report_templates import REQUIRED_CHAPTERS, validate_manifest

MAX_UNCOMPRESSED_BYTES = 200 * 1024 * 1024  # 200MB
ALLOWED_SUFFIX = (".docx", ".json")


class TemplatePackageError(Exception):
    """模板包校验/导入失败（中文消息）。"""


def _safe_member(name):
    """ZIP 成员路径安全化；非法返回 None。"""
    raw = str(name or "").replace("\\", "/")
    if raw.startswith("/") or raw.startswith("../") or ".." in raw.split("/"):
        return None
    parts = [p for p in raw.split("/") if p not in ("", ".")]
    if not parts:
        return None
    if len(parts[0]) >= 2 and parts[0][1] == ":":
        return None
    return "/".join(parts)


def safe_extract_zip(zip_path, dest_dir):
    """安全解压模板包；返回 (extracted_files, warnings)。"""
    dest_dir = os.path.abspath(dest_dir)
    os.makedirs(dest_dir, exist_ok=True)
    warnings = []
    extracted = []
    try:
        with zipfile.ZipFile(zip_path, "r") as zf:
            total = sum(int(info.file_size or 0) for info in zf.infolist())
            if total > MAX_UNCOMPRESSED_BYTES:
                raise TemplatePackageError("模板包解压后超过 200MB，已拒绝导入")
            for info in zf.infolist():
                if info.is_dir():
                    continue
                name = _safe_member(info.filename)
                if name is None:
                    warnings.append("已跳过非法路径：%s" % info.filename)
                    continue
                if not name.lower().endswith(ALLOWED_SUFFIX):
                    warnings.append("已跳过非模板文件：%s" % name)
                    continue
                target = os.path.join(dest_dir, *name.split("/"))
                if os.path.commonpath([dest_dir, os.path.abspath(target)]) != dest_dir:
                    warnings.append("已跳过越界路径：%s" % name)
                    continue
                parent = os.path.dirname(target)
                if parent:
                    os.makedirs(parent, exist_ok=True)
                with zf.open(info, "r") as src, open(target, "wb") as dst:
                    while True:
                        chunk = src.read(1024 * 256)
                        if not chunk:
                            break
                        dst.write(chunk)
                extracted.append(name)
    except TemplatePackageError:
        raise
    except zipfile.BadZipFile:
        raise TemplatePackageError("上传文件不是有效的 ZIP 模板包")
    except Exception as e:  # noqa: BLE001
        raise TemplatePackageError("解压模板包失败：%s" % e)
    if not extracted:
        raise TemplatePackageError("模板包内没有可导入的 .docx/.json 文件")
    return extracted, warnings


def find_package_root(extracted_dir):
    """定位 manifest.json 所在目录（支持多一层根目录）。"""
    extracted_dir = os.path.abspath(extracted_dir)
    direct = os.path.join(extracted_dir, "manifest.json")
    if os.path.isfile(direct):
        return extracted_dir
    candidates = []
    for name in sorted(os.listdir(extracted_dir)):
        path = os.path.join(extracted_dir, name)
        if os.path.isdir(path) and os.path.isfile(os.path.join(path, "manifest.json")):
            candidates.append(path)
    if len(candidates) == 1:
        return candidates[0]
    if len(candidates) > 1:
        raise TemplatePackageError("模板包中存在多个 manifest.json，无法确定根目录")
    # 再向下找一层
    for name in sorted(os.listdir(extracted_dir)):
        path = os.path.join(extracted_dir, name)
        if not os.path.isdir(path):
            continue
        for sub in sorted(os.listdir(path)):
            sub_path = os.path.join(path, sub)
            if os.path.isdir(sub_path) and os.path.isfile(
                    os.path.join(sub_path, "manifest.json")):
                candidates.append(sub_path)
    if len(candidates) == 1:
        return candidates[0]
    raise TemplatePackageError("模板包缺少 manifest.json（请先导出内置模板包查看格式）")


def read_manifest(package_root):
    path = os.path.join(package_root, "manifest.json")
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception as e:  # noqa: BLE001
        raise TemplatePackageError("manifest.json 不是有效的 JSON：%s" % e)
    if not isinstance(data, dict):
        raise TemplatePackageError("manifest.json 必须是对象")
    error = validate_manifest(data)
    if error:
        raise TemplatePackageError(error)
    return data


def _safe_join(root, rel):
    """把 manifest 相对路径安全拼到目录下（拒绝 .. / 绝对路径）。"""
    text = str(rel or "").replace("\\", "/").strip().lstrip("/")
    parts = [p for p in text.split("/") if p not in ("", ".")]
    if any(p == ".." for p in parts):
        raise TemplatePackageError("模板路径不允许包含 ..：%s" % rel)
    return os.path.join(root, *parts)


def validate_package_files(package_root, manifest):
    """校验章节/结果表文件存在且为有效 docx；返回 warnings。"""
    warnings = []
    chapters = manifest.get("chapters") or {}
    for key in REQUIRED_CHAPTERS:
        rel = str(chapters.get(key) or "").replace("\\", "/")
        path = _safe_join(package_root, rel)
        if not os.path.isfile(path):
            raise TemplatePackageError("模板包缺少章节文件：%s（%s）" % (key, rel))
        if not path.lower().endswith(".docx"):
            raise TemplatePackageError("章节文件必须是 .docx：%s" % rel)
        try:
            Document(path)
        except Exception as e:  # noqa: BLE001
            raise TemplatePackageError("章节文件不是有效的 .docx：%s（%s）" % (rel, e))
    for i, item in enumerate(manifest.get("result_tables") or []):
        rel = str(item.get("file") or "").replace("\\", "/")
        path = _safe_join(package_root, rel)
        if not os.path.isfile(path):
            raise TemplatePackageError("结果表文件不存在：%s" % rel)
        if not path.lower().endswith(".docx"):
            raise TemplatePackageError("结果表文件必须是 .docx：%s" % rel)
        try:
            doc = Document(path)
        except Exception as e:  # noqa: BLE001
            raise TemplatePackageError("结果表不是有效的 .docx：%s（%s）" % (rel, e))
        if not doc.tables:
            warnings.append("结果表模板中没有表格：%s" % rel)
    return warnings


def load_report_package(zip_path, work_dir):
    """解压 + 定位 + 校验；返回 (package_root, manifest, warnings)。"""
    _files, warnings = safe_extract_zip(zip_path, work_dir)
    package_root = find_package_root(work_dir)
    manifest = read_manifest(package_root)
    warnings.extend(validate_package_files(package_root, manifest))
    return package_root, manifest, warnings


def export_report_package(root, manifest, output_zip):
    """把模板目录 + manifest 打成 ZIP（跳过 ~$ 临时文件）。"""
    root = os.path.abspath(root)
    output_zip = os.path.abspath(output_zip)
    parent = os.path.dirname(output_zip)
    if parent:
        os.makedirs(parent, exist_ok=True)
    data = dict(manifest or {})
    data.setdefault("schema", "report_template_v1")
    with zipfile.ZipFile(output_zip, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("manifest.json",
                    json.dumps(data, ensure_ascii=False, indent=2))
        for dirpath, _dirnames, filenames in os.walk(root):
            for filename in filenames:
                if filename.startswith("~$"):
                    continue
                if filename.lower() == "manifest.json":
                    continue
                if not filename.lower().endswith(".docx"):
                    continue
                full = os.path.join(dirpath, filename)
                rel = os.path.relpath(full, root).replace("\\", "/")
                zf.write(full, rel)
    return output_zip
