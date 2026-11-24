# 回归测试

统一由 `scripts/check.ps1` 调用（23 个套件 × 系统 Python 3.8 与 `.venv` 3.14）。

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\check.ps1
python tests/test_report_facts.py          # 单个套件
```

## 约定

- 新脚本用共用骨架，不要复制样板：
  ```python
  import _harness
  ROOT = _harness.bootstrap()      # libs / report_generator / 项目根 / webapp / backend
  _harness.utf8_stdio()
  from _harness import Results
  _R = Results(); check = _R.check
  def main():
      check("断言", True)
      return _R.finish()
  ```
- 旧脚本里的 `ROOT = 上一级` 写法仍兼容；
- 临时目录必须用 `tempfile.mkdtemp` 并在 `finally` 里 `shutil.rmtree`（自检会检查根目录残留）；
- 输出统一 UTF-8（脚本内 `sys.stdout.reconfigure` 或由 check.ps1 设置 `PYTHONIOENCODING`）；
- 不修改真实工程/记录库：需要写操作的用临时工程文件并在结束时恢复。

## 不进入自检

`legacy/` 下是桌面端旧冒烟（需要 PyQt5、会改真实工程），只在人工验证时单独运行。
