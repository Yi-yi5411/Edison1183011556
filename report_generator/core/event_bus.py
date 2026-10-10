# -*- coding: utf-8 -*-
"""事件总线：解耦 UI 与业务层的轻量级发布/订阅。

UI 与控制器通过事件总线通信，避免直接相互依赖。采用 Qt 无关的纯 Python
实现，便于非 GUI 代码复用。

约定事件名（字符串）：
  - "sheet.activated"   工作表切换
  - "cell.changed"      单元格内容变化
  - "project.saved"     项目已保存
  - "project.loaded"    项目已加载
  - "export.done"       导出完成
"""


class EventBus:
    def __init__(self):
        self._handlers = {}  # event_name -> [callable]

    def subscribe(self, event_name, handler):
        """订阅事件，同一处理器仅注册一次。"""
        lst = self._handlers.setdefault(event_name, [])
        if handler not in lst:
            lst.append(handler)

    def unsubscribe(self, event_name, handler):
        lst = self._handlers.get(event_name, [])
        if handler in lst:
            lst.remove(handler)

    def emit(self, event_name, *args, **kwargs):
        """触发事件；单个处理器异常不影响其他处理器。"""
        for h in list(self._handlers.get(event_name, [])):
            try:
                h(*args, **kwargs)
            except Exception:
                pass


# ── 全局总线单例 ──
_bus = None


def get_event_bus():
    global _bus
    if _bus is None:
        _bus = EventBus()
    return _bus
