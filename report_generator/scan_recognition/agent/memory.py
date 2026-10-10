# -*- coding: utf-8 -*-
"""识别智能体的记忆体系（长期记忆 + 短期记忆 + 上下文压缩）。

- 长期记忆（scan_memory 表，跨会话持久）：人工校正差异、量程治理留痕
  学习为"校正经验"；识别时按检测项目召回、压缩聚合后注入视觉转写
  提示词，让识别越用越准。
- 短期记忆（进程内会话字典）：同一张图短期内重复识别时，把上一轮的
  治理留痕/可疑清单立即注入本轮提示词（不必等人工校正沉淀为长期
  经验）；LRU 容量上限 + TTL 过期即上下文压缩。
- 上下文压缩：召回的记忆按出现次数聚合排序、超过 max_hints 的折叠为
  一句摘要；会话记忆超容量淘汰最旧。

存储层只负责读写（ScanDatabase.remember_correction 等），
本模块负责学习策略、压缩与提示词文本生成。
"""
import time


class MemoryStore:
    """识别记忆管理器：长期记忆（SQLite）+ 短期会话记忆（进程内）。"""

    # 短期记忆：最多保留的图片数（LRU 淘汰）与有效期（秒）
    SESSION_CAPACITY = 8
    SESSION_TTL = 30 * 60
    # 单次校正最多学习条数（防止批量误操作灌爆记忆）
    LEARN_LIMIT = 30

    def __init__(self, db, cfg=None):
        self.db = db
        n = (cfg.memory if cfg else None) or {}
        self.enabled = n.get("enabled", True)
        self.max_hints = int(n.get("max_hints", 8))
        self.session_cache = n.get("session_cache", True)
        # 短期记忆：file_hash -> {"ts": 时间戳, "hints": [str, ...],
        #                        "summary": 上轮识别摘要}
        self._session = {}

    # ── 长期记忆：学习 ──
    def learn_from_correction(self, detection_item, columns, old_rows,
                              new_rows):
        """从人工校正前后差异中学习（对齐行按列名 diff）。

        old_rows/new_rows 为等长对齐行（列表的列表），列与 columns 对应；
        单次最多记 LEARN_LIMIT 条，防止批量操作灌爆记忆。
        返回本条学习到的记忆条数。
        """
        if not self.enabled or not self.db:
            return 0
        learned = 0
        for i, new_row in enumerate(new_rows or []):
            if i >= len(old_rows or []):
                break
            old_row = old_rows[i]
            for j, field in enumerate(columns or []):
                if learned >= self.LEARN_LIMIT:
                    return learned
                try:
                    old_v = str(old_row[j] if j < len(old_row) else "")
                    new_v = str(new_row[j] if j < len(new_row) else "")
                except Exception:
                    continue
                if old_v == new_v or not (old_v or new_v):
                    continue
                self.db.remember_correction(
                    detection_item, field, old_v, new_v,
                    note="人工校正")
                learned += 1
        return learned

    def learn_patterns(self, detection_item, field_warnings):
        """把量程治理留痕（如"3 被按未测清空"）学习为误识模式。"""
        if not self.enabled or not self.db:
            return 0
        learned = 0
        for w in field_warnings or []:
            if learned >= self.LEARN_LIMIT:
                break
            if "自动清空" not in str(w.get("问题") or ""):
                continue
            self.db.remember_correction(
                detection_item, str(w.get("字段") or ""),
                str(w.get("值") or ""), "", kind="pattern",
                note="未测斜杠/被误识为数字")
            learned += 1
        return learned

    # ── 长期记忆：召回 + 上下文压缩 ──
    def recall_hints(self, detection_item):
        """召回该检测项目的校正经验并压缩为提示词文本（无则空串）。

        压缩策略：按出现次数降序取前 max_hints 条；其余折叠为一句
        摘要，避免提示词随记忆增长无限膨胀。
        """
        if not self.enabled or not self.db:
            return ""
        try:
            items = self.db.list_memory(detection_item)
        except Exception:
            return ""
        if not items:
            return ""
        lines = []
        for m in items[:max(1, self.max_hints)]:
            old_v = str(m.get("old_value") or "")
            new_v = str(m.get("new_value") or "")
            field = str(m.get("field") or "")
            cnt = m.get("count") or 1
            new_desc = f"实为「{new_v}」" if new_v else "实为未测（/）或空白"
            lines.append(
                f"- 字段「{field}」识别「{old_v}」{new_desc}"
                f"（出现{cnt}次）")
        extra = len(items) - len(lines)
        text = "历史校正经验（仅供对照参考，仍必须以图片实际内容为准，禁止照抄经验值）：\n" \
            + "\n".join(lines)
        if extra > 0:
            text += f"\n- 另有{extra}处零星历史修正，转写时请仔细核对。"
        return text

    # ── 短期记忆（进程内会话） ──
    def remember_session(self, file_hash, hints, summary=""):
        """记录一次识别的短期上下文（治理留痕/可疑清单 + 摘要）。"""
        if not self.session_cache or not file_hash:
            return
        self._compress_session()
        self._session[file_hash] = {
            "ts": time.time(), "hints": list(hints or []),
            "summary": str(summary or "")}

    def recall_session(self, file_hash):
        """召回同图短期记忆（已过期/不存在返回 None）。"""
        if not self.session_cache or not file_hash:
            return None
        item = self._session.get(file_hash)
        if not item:
            return None
        if time.time() - item["ts"] > self.SESSION_TTL:
            self._session.pop(file_hash, None)
            return None
        return item

    def compose_hints(self, detection_item, file_hash):
        """合并长期记忆与短期会话记忆为注入文本，返回 (文本, 命中条数)。

        短期记忆（同图上轮复核留痕）在前、优先级高；长期校正经验在后。
        任何异常静默降级为空（记忆不可用不能影响识别主流程）。
        """
        parts, n = [], 0
        try:
            sess = self.recall_session(file_hash)
            if sess and sess.get("hints"):
                hs = list(sess["hints"])[:max(1, self.max_hints)]
                lines = [
                    f"- 行{w.get('行')} 字段「{w.get('字段')}」"
                    f"值「{w.get('值')}」：{w.get('问题')}" for w in hs]
                parts.append("上次识别本图的复核留痕"
                             "（本次请重点核对这些位置）：\n"
                             + "\n".join(lines))
                n += len(lines)
        except Exception:
            pass
        try:
            lt = self.recall_hints(detection_item)
            if lt:
                parts.append(lt)
                if self.db:
                    n += min(max(1, self.max_hints),
                             len(self.db.list_memory(detection_item)))
        except Exception:
            pass
        return "\n".join(parts), n

    def _compress_session(self):
        """短期记忆上下文压缩：超容量 LRU 淘汰最旧。"""
        if len(self._session) < self.SESSION_CAPACITY:
            return
        for h in sorted(self._session, key=lambda k: self._session[k]["ts"])[
                :len(self._session) - self.SESSION_CAPACITY + 1]:
            self._session.pop(h, None)
