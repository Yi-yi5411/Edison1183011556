# -*- coding: utf-8 -*-
"""测试公共骨架：路径引导、UTF-8 输出、断言计数与汇总。

用法（tests/ 下的脚本）：

    import _harness
    ROOT = _harness.bootstrap()          # 加好 libs/report_generator/root/webapp/backend
    _harness.utf8_stdio()

    from _harness import Results
    _R = Results()
    check = _R.check
    skip = _R.skip

    def main():
        check("某个断言", True)
        return _R.finish("报告事实")     # 打印汇总并返回退出码

约定：一个脚本只建一个 Results；不写真实工程；临时目录自清理。
"""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def bootstrap(*extra):
    """把项目常用路径加入 sys.path，返回项目根目录。"""
    paths = [os.path.join(ROOT, "report_generator", "libs"),
             os.path.join(ROOT, "report_generator"), ROOT,
             os.path.join(ROOT, "webapp"),
             os.path.join(ROOT, "webapp", "backend")]
    paths.extend(extra)
    for path in paths:
        if os.path.isdir(path) and path not in sys.path:
            sys.path.insert(0, path)
    return ROOT


def utf8_stdio():
    """控制台/重定向可能是 cp936，统一按 UTF-8 输出（失败忽略）。"""
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:  # noqa: BLE001
            pass


class Results:
    """断言计数器：check/skip + 统一汇总。"""

    def __init__(self):
        self.items = []

    def check(self, desc, ok, got=None):
        self.items.append((desc, bool(ok)))
        print(("PASS" if ok else "FAIL"), desc, "->", repr(got))
        return bool(ok)

    def skip(self, desc, why=""):
        print("SKIP", desc, "->", why)

    # 兼容旧脚本里的 “RESULTS 列表” 写法
    @property
    def results(self):
        return self.items

    def finish(self, title=""):
        fails = [desc for desc, ok in self.items if not ok]
        print("=" * 50)
        if title:
            print("【%s】" % title)
        print("%d/%d PASS" % (len(self.items) - len(fails), len(self.items)))
        if fails:
            print("FAILED:", fails[:10] if len(fails) > 10 else fails)
        return 1 if fails else 0
