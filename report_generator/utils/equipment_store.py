# -*- coding: utf-8 -*-
"""检测设备库：本地 SQLite 存储 + 设备管理系统字段归一化。

设备数据由设备管理系统同步而来；本地库保存报告需要的字段和“是否用于报告”选择。
"""
import json
import os
import sqlite3
import threading
import uuid
from datetime import datetime

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_DB_DIR = os.path.join(_ROOT, "data", "equipment")
_DB_PATH = os.path.join(_DB_DIR, "equipment.db")
_LOCK = threading.RLock()

_SCHEMA = """
CREATE TABLE IF NOT EXISTS equipment (
    id TEXT PRIMARY KEY,
    remote_id TEXT UNIQUE,
    name TEXT NOT NULL DEFAULT '',
    category_code TEXT DEFAULT '',
    cert_no TEXT DEFAULT '',
    last_check_date TEXT DEFAULT '',
    next_check_date TEXT DEFAULT '',
    model TEXT DEFAULT '',
    manufacturer TEXT DEFAULT '',
    status TEXT DEFAULT '',
    owner TEXT DEFAULT '',
    department TEXT DEFAULT '',
    location TEXT DEFAULT '',
    selected INTEGER NOT NULL DEFAULT 1,
    raw_json TEXT DEFAULT '',
    synced_at TEXT DEFAULT ''
);
CREATE INDEX IF NOT EXISTS idx_equipment_name ON equipment(name);
CREATE TABLE IF NOT EXISTS equipment_usage (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    usage_date TEXT NOT NULL,
    equipment_id TEXT NOT NULL,
    report_key TEXT NOT NULL,
    created_at TEXT DEFAULT '',
    UNIQUE(usage_date, equipment_id, report_key)
);
CREATE INDEX IF NOT EXISTS idx_equipment_usage_day
    ON equipment_usage(usage_date, equipment_id);
"""


def _connect():
    os.makedirs(_DB_DIR, exist_ok=True)
    conn = sqlite3.connect(_DB_PATH, timeout=10)
    conn.row_factory = sqlite3.Row
    conn.executescript(_SCHEMA)
    return conn


def normalize_remote(rec):
    """把设备管理系统记录转成本地库字段。"""
    rec = rec if isinstance(rec, dict) else {}
    remote_id = str(rec.get("id") or "").strip() or uuid.uuid4().hex
    return {
        "id": remote_id,
        "remote_id": remote_id,
        "name": str(rec.get("equipmentName") or "").strip(),
        "category_code": str(rec.get("equipmentId1") or rec.get("equipmentId3") or "").strip(),
        "cert_no": str(rec.get("code") or "").strip(),
        "last_check_date": str(rec.get("codetwo") or "").strip(),
        "next_check_date": str(rec.get("equipmentDate") or "").strip(),
        "model": str(rec.get("equipmentType1") or "").strip(),
        "manufacturer": str(rec.get("equipmentManufactor") or "").strip(),
        "status": str(rec.get("equipmentId5_dictText") or rec.get("equipmentId5") or "").strip(),
        "owner": str(rec.get("codes") or "").strip(),
        "department": str(rec.get("equipmentPlace2_dictText") or rec.get("equipmentPlace2") or "").strip(),
        "location": str(rec.get("equipmentPlace") or "").strip(),
        "raw_json": json.dumps(rec, ensure_ascii=False),
        "synced_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }


def upsert_equipment(items, selected=True):
    rows = [normalize_remote(x) for x in (items or []) if isinstance(x, dict)]
    if not rows:
        return 0
    with _LOCK, _connect() as conn:
        for row in rows:
            conn.execute(
                """INSERT INTO equipment
                   (id, remote_id, name, category_code, cert_no, last_check_date,
                    next_check_date, model, manufacturer, status, owner,
                    department, location, selected, raw_json, synced_at)
                   VALUES (:id, :remote_id, :name, :category_code, :cert_no,
                           :last_check_date, :next_check_date, :model,
                           :manufacturer, :status, :owner, :department,
                           :location, :selected, :raw_json, :synced_at)
                   ON CONFLICT(remote_id) DO UPDATE SET
                     name=excluded.name,
                     category_code=excluded.category_code,
                     cert_no=excluded.cert_no,
                     last_check_date=excluded.last_check_date,
                     next_check_date=excluded.next_check_date,
                     model=excluded.model,
                     manufacturer=excluded.manufacturer,
                     status=excluded.status,
                     owner=excluded.owner,
                     department=excluded.department,
                     location=excluded.location,
                     raw_json=excluded.raw_json,
                     synced_at=excluded.synced_at""",
                {**row, "selected": 1 if selected else 0})
    return len(rows)


def _row_to_dict(row):
    d = dict(row)
    d["selected"] = bool(d.get("selected"))
    d["remote_id"] = d.get("remote_id") or d.get("id")
    return d


def list_equipment(query="", selected_only=False, limit=500):
    q = str(query or "").strip()
    sql = "SELECT * FROM equipment"
    params = []
    where = []
    if q:
        where.append("(name LIKE ? OR category_code LIKE ? OR cert_no LIKE ? OR model LIKE ?)")
        like = "%" + q + "%"
        params.extend([like, like, like, like])
    if selected_only:
        where.append("selected=1")
    if where:
        sql += " WHERE " + " AND ".join(where)
    sql += " ORDER BY selected DESC, name COLLATE NOCASE LIMIT ?"
    params.append(int(limit))
    with _LOCK, _connect() as conn:
        return [_row_to_dict(r) for r in conn.execute(sql, params).fetchall()]


def set_selected(ids, selected):
    ids = [str(x) for x in (ids or []) if str(x).strip()]
    if not ids:
        return 0
    marks = ",".join("?" for _ in ids)
    with _LOCK, _connect() as conn:
        cur = conn.execute(
            "UPDATE equipment SET selected=? WHERE id IN (%s)" % marks,
            [1 if selected else 0] + ids)
        return cur.rowcount


def delete_equipment(ids):
    ids = [str(x) for x in (ids or []) if str(x).strip()]
    if not ids:
        return 0
    marks = ",".join("?" for _ in ids)
    with _LOCK, _connect() as conn:
        cur = conn.execute("DELETE FROM equipment WHERE id IN (%s)" % marks, ids)
        return cur.rowcount


def count_equipment():
    with _LOCK, _connect() as conn:
        return conn.execute("SELECT COUNT(*) FROM equipment").fetchone()[0]


def report_equipment_rows(limit=6):
    """报告第三章使用：优先选中的设备；没有选中时取全部。"""
    rows = list_equipment(selected_only=True, limit=limit)
    return [{
        "设备名称": r.get("name", ""),
        "设备分类编号": r.get("category_code", ""),
        "最近检定日期": r.get("last_check_date", ""),
        "检定证书编号": r.get("cert_no", ""),
    } for r in rows if r.get("name")]


class EquipmentUnavailable(Exception):
    """没有满足“在用 + 当日未满 10 次”的仪器。"""


_DAILY_LIMIT = 10
_MATCH_RULES = {
    "混凝土回弹仪": {
        "include": ("回弹仪",),
        "exclude": (
            "砂浆", "砖", "弯沉", "沥青", "路面", "高强",
            "游标卡尺", "率定", "钢砧", "试块", "校准", "检定",
        ),
    },
    "一体式钢筋扫描仪": {
        "include": ("钢筋扫描", "钢筋检测", "钢筋探测"),
        "exclude": ("率定", "试块", "校准"),
    },
    "微控电液伺服压力试验机": {
        "include": ("压力试验机",),
        "exclude": (
            "井盖", "陶瓷", "抗折", "沥青", "幕墙", "泌水",
            "压力表", "变送器", "氧指数", "率定", "试块", "校准",
        ),
        "prefer": ("电液伺服", "微控", "微机控制", "数显"),
    },
    "一体式楼板测厚仪": {
        "include": ("测厚",),
        "exclude": ("率定", "试块", "校准"),
    },
    "一体式墙体拉结筋检测仪": {
        "include": ("拉结筋",),
        "exclude": ("率定", "试块", "校准"),
    },
    # ── P4-3：砖混/砌体/钢构/木结构等项目的专用仪器 ──
    # include：任一命中即算；all：必须全部命中；exclude：任一命中即排除
    "砖回弹仪": {
        "include": ("砖回弹仪",),
        "exclude": ("率定", "钢砧", "试块", "校准", "检定"),
    },
    "贯入式砂浆强度检测仪": {
        "all": ("贯入", "砂浆"),
        "exclude": ("率定", "试块", "校准", "阻力", "标准贯入"),
    },
    "锚杆拉拔仪": {
        "include": ("拉拔", "拉力计"),
        "exclude": ("压力机", "试验机", "桩", "率定", "试块", "油漆", "涂层", "推拉"),
        "prefer": ("数显", "锚杆", "一体式"),
    },
    "高强螺栓扭矩系数测定仪": {
        "all": ("螺栓", "扭矩"),
        "exclude": ("率定", "试块", "校准", "板子", "扳手"),
    },
    "涂层测厚仪": {
        "all": ("测厚",),
        "include": ("涂层", "涂镀层", "涂膜"),
        "exclude": ("率定", "试块", "校准"),
    },
    "金属硬度计": {
        "include": ("硬度计",),
        "exclude": ("涂膜", "铅笔", "划痕", "率定", "试块"),
    },
    "超声波探伤仪": {
        "all": ("超声", "探伤"),
        "exclude": ("加湿器", "流量计", "桩", "率定"),
    },
    "钢卷尺": {
        "include": ("卷尺",),
        "exclude": ("率定", "试块", "校准"),
    },
    "钢直尺": {
        "include": ("钢直尺", "直尺"),
        "exclude": ("率定", "试块", "校准", "塞尺"),
    },
    "百分表": {
        "include": ("百分表",),
        "exclude": ("率定", "试块", "校准"),
    },
    "游标卡尺": {
        "include": ("游标卡尺", "数显卡尺", "卡尺"),
        "exclude": ("砖用", "砖", "塞尺", "深度", "千分", "高度", "消防", "率定", "试块", "校准"),
    },
}


def _manifest_equipment(key):
    """读 manifest 里声明的设备名。

    返回 None 表示「没有 manifest 覆盖这个项目」（调用方回退）；
    返回 [] 表示「项目明确不需要专用仪器」。
    """
    try:
        from structural_items import find_item
    except Exception:  # noqa: BLE001
        return None
    try:
        found = find_item(key)
    except Exception:  # noqa: BLE001
        return None
    if not found:
        return None
    _entry, item = found
    names = item.get("equipment")
    if names is None:
        return None
    return [str(name).strip() for name in names if str(name).strip()]


def _required_instruments(checked_order):
    """按检测项目汇总报告需要的仪器名（manifest 优先）。"""
    try:
        from utils.report_narrative import equipment_for
    except ImportError:  # noqa: BLE001
        from report_generator.utils.report_narrative import equipment_for
    names = []
    try:
        from core.plugin_manager import get_plugin_manager
        manager = get_plugin_manager()
    except Exception:  # noqa: BLE001
        manager = None
    for key in checked_order or []:
        declared = _manifest_equipment(key)
        if declared is None:
            plugin = manager.get_plugin_for_item(key) if manager else None
            declared = []
            if plugin is not None and hasattr(plugin, "required_instruments"):
                try:
                    declared = plugin.required_instruments()
                except Exception:  # noqa: BLE001
                    declared = []
            if not declared:
                declared = [str((row or {}).get("设备名称") or "").strip()
                            for row in equipment_for([key])]
        for name in declared:
            name = str(name or "").strip()
            if name and name not in names:
                names.append(name)
    return names


def _instrument_matches(required, name):
    required = str(required or "").strip()
    name = str(name or "").strip()
    if not required or not name:
        return False
    rule = _MATCH_RULES.get(required)
    if rule:
        if any(word in name for word in rule.get("exclude", ())):
            return False
        required_all = rule.get("all") or ()
        if required_all and not all(word in name for word in required_all):
            return False
        includes = rule.get("include") or ()
        if includes and not any(word in name for word in includes):
            return False
        return True
    # 未配置规则时只做保守的完整包含匹配，避免把配件当仪器
    if any(word in name for word in ("率定", "钢砧", "试块", "标准器", "校准")):
        return False
    return required in name or name in required


def _prefer_score(required, name):
    """规则里的优先词命中越多越靠前（数显锚杆拉拔仪优先于普通拉拔仪）。"""
    rule = _MATCH_RULES.get(required) or {}
    prefer = rule.get("prefer") or ()
    score = 0
    for index, word in enumerate(prefer):
        if word in name:
            score += (len(prefer) - index) * 10
    return score


def _today():
    return datetime.now().strftime("%Y-%m-%d")


def _active_equipment_with_usage(conn, day):
    rows = [dict(r) for r in conn.execute(
        "SELECT * FROM equipment WHERE status='在用' ORDER BY name, id")]
    usage = {row[0]: row[1] for row in conn.execute(
        "SELECT equipment_id, COUNT(*) FROM equipment_usage "
        "WHERE usage_date=? GROUP BY equipment_id", (day,))}
    for row in rows:
        row["_usage"] = int(usage.get(row.get("id"), 0))
    return rows


def _pick_equipment(conn, checked_order, day):
    """按检测项目选仪器；返回 (rows, missing)。"""
    required = _required_instruments(checked_order)
    if not required:
        return [], []
    active = _active_equipment_with_usage(conn, day)
    used = set()
    rows = []
    missing = []
    for name in required:
        candidates = [
            row for row in active
            if row.get("id") not in used
            and row.get("_usage", 0) < _DAILY_LIMIT
            and _instrument_matches(name, row.get("name"))
        ]
        candidates.sort(key=lambda row: (
            -_prefer_score(name, row.get("name") or ""),
            0 if row.get("selected") else 1,
            str(row.get("id") or ""),
        ))
        if not candidates:
            missing.append(name)
            rows.append({
                "设备名称": name,
                "设备分类编号": "",
                "最近检定日期": "",
                "检定证书编号": "",
                "今日使用": "—",
                "每日上限": _DAILY_LIMIT,
                "是否可用": "无可用仪器",
                "_missing": True,
            })
            continue
        row = candidates[0]
        used.add(row.get("id"))
        rows.append({
            "设备名称": row.get("name", ""),
            "设备分类编号": row.get("category_code", ""),
            "最近检定日期": row.get("last_check_date", ""),
            "检定证书编号": row.get("cert_no", ""),
            "今日使用": row.get("_usage", 0),
            "每日上限": _DAILY_LIMIT,
            "是否可用": "可用",
            "_equipment_id": row.get("id"),
        })
    return rows, missing


def preview_equipment_for_report(checked_order, limit=20, day=None):
    """预览报告将使用的仪器；不占用当日次数。"""
    day = day or _today()
    with _LOCK, _connect() as conn:
        rows, _missing = _pick_equipment(conn, checked_order, day)
    return rows[:limit]


def preview_equipment_detail(checked_items, limit=5, day=None):
    """逐检测项目给出候选仪器与推荐理由（不占用当日次数）。

    返回 [{item, required, candidates: [{name, usage, selected, available,
    reason}], missing}]，用于解释「为什么推荐这台设备」。
    """
    day = day or _today()
    detail = []
    with _LOCK, _connect() as conn:
        active = _active_equipment_with_usage(conn, day)
    for key in checked_items or []:
        names = _required_instruments([key])
        candidates = []
        missing = []
        for name in names:
            matches = [row for row in active
                       if _instrument_matches(name, row.get("name"))]
            matches.sort(key=lambda row: (
                row.get("_usage", 0) >= _DAILY_LIMIT,
                0 if row.get("selected") else 1,
                str(row.get("id") or "")))
            usable = [row for row in matches
                      if row.get("_usage", 0) < _DAILY_LIMIT]
            if not usable:
                missing.append(name)
            for row in matches[:max(1, int(limit or 5))]:
                usage = int(row.get("_usage", 0))
                available = usage < _DAILY_LIMIT
                reasons = ["在用"]
                reasons.append("当日报用 %d/%d 次" % (usage, _DAILY_LIMIT))
                if row.get("selected"):
                    reasons.append("已选入报告")
                if not available:
                    reasons.append("今日已达上限，需换一台或改日")
                else:
                    reasons.append("可选用")
                candidates.append({
                    "required": name,
                    "name": row.get("name", ""),
                    "category_code": row.get("category_code", ""),
                    "cert_no": row.get("cert_no", ""),
                    "last_check_date": row.get("last_check_date", ""),
                    "usage": usage,
                    "daily_limit": _DAILY_LIMIT,
                    "selected": bool(row.get("selected")),
                    "available": available,
                    "reason": "推荐：" + "、".join(reasons) if available
                              else "不可用：" + "、".join(reasons),
                })
        detail.append({
            "item": key,
            "required": names,
            "candidates": candidates,
            "missing": missing,
            "covered": not missing if names else True,
        })
    return detail


def reserve_equipment_for_report(checked_order, report_key):
    """生成报告时占用仪器当日 1 次；无可用仪器则抛错。"""
    day = _today()
    with _LOCK, _connect() as conn:
        rows, missing = _pick_equipment(conn, checked_order, day)
        if missing:
            raise EquipmentUnavailable(
                "以下检测项目没有“在用且今日未满10次”的仪器：%s"
                % "、".join(missing))
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        for row in rows:
            equipment_id = row.get("_equipment_id")
            if not equipment_id:
                continue
            conn.execute(
                "INSERT OR IGNORE INTO equipment_usage "
                "(usage_date, equipment_id, report_key, created_at) "
                "VALUES (?,?,?,?)",
                (day, equipment_id, str(report_key), now))
            row["今日使用"] = int(row.get("今日使用") or 0) + 1
        conn.commit()
    return rows


def release_equipment_for_report(report_key):
    """报告生成失败时释放已占用的次数。"""
    with _LOCK, _connect() as conn:
        conn.execute("DELETE FROM equipment_usage WHERE report_key=?",
                     (str(report_key),))
        conn.commit()


def report_equipment_rows_for(checked_order, limit=20):
    """报告第三章使用：按检测项目选择“在用且当日未满10次”的仪器。"""
    return preview_equipment_for_report(checked_order, limit=limit)
