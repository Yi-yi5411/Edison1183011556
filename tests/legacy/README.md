# 桌面端旧冒烟（不进入自检）

| 脚本 | 说明 | 注意 |
|---|---|---|
| `test_cover_point_smoke.py` | 保护层测点录入对话框 + 原始记录 COM 填充 | 需要 PyQt5，离屏模式；COM 不可用时 SKIP |
| `test_fill_target_smoke.py` | 按识别类型定位检测项目的填充目标 | 需要 PyQt5，离屏模式 |
运行方式（项目根目录）：

```powershell
python tests/legacy/test_fill_target_smoke.py
```

新功能请优先写 `tests/test_*.py` 并加入 `scripts/check.ps1`。
