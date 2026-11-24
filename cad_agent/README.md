# 探索者 TSDP2024 CAD 智能体

通过自然语言（中文）在 AutoCAD 2020 上生成 CAD 图纸。探索者 TSDP2024 是架设在
AutoCAD 2020（R23.1 / 简体中文）上的结构绘图平台，本智能体提供两种后端：

- **在线模式**：通过 `pywin32` 的 AutoCAD ActiveX/COM 接口，把图元直接画进正在运行的 AutoCAD。
- **离线模式**：未连接 AutoCAD 时自动回退，生成 R12 DXF 文件，可在探索者/AutoCAD 中打开。

图纸单位统一为 **毫米**。

## 环境

- 探索者 TSDP2024：`D:\Program Files\TszCAD\TSDP2024`
- AutoCAD 2020：`D:\Program Files\Autodesk\AutoCAD 2020`
- Python 3.8（本机 `C:\Program Files\python`，已装 `pywin32`）

## 使用

先打开探索者（二选一）：

```bat
start "" "D:\Program Files\TszCAD\TSDP2024\TSDPRun.exe"
```

或在工作目录双击 `打开探索者.bat`。

然后启动智能体：

```bat
cd /d "C:\Users\Administrator\Desktop\科技创新\地震损伤模型"
python -m cad_agent.cli
```

一次执行一条命令：

```bat
python -m cad_agent.cli "画一个3×4轴网，开间6米，进深7.2米"
```

生成示例图（离线 DXF，可立即验证链路）：

```bat
python -m cad_agent.demo
```

## 支持的指令示例

| 自然语言 | 效果 |
| --- | --- |
| `打开探索者` | 启动 TSDP2024 并连接 AutoCAD |
| `画一个3×4轴网，开间6米，进深7.2米` | 绘制轴网并标注轴号 |
| `在(0,0)画一个400×400的柱` | 绘制柱（COLUMN 层） |
| `画一条梁，长6米，截面300×600` | 绘制梁（BEAM 层） |
| `画一堵240厚的墙，长8米` | 绘制墙（WALL 层） |
| `画一个矩形，6000×3000` | 绘制矩形 |
| `画一个圆，圆心(3000,0)，半径500` | 绘制圆 |
| `写"一层平面图"，字高400` | 写单行文字 |
| `尺寸标注 (0,0) 到 (6000,0)` | 添加尺寸标注 |
| `保存` / `保存到"D:\out.dwg"` | 保存（在线 DWG / 离线 DXF） |
| `缩放` | 缩放到图形范围 |
| `退出` | 结束智能体 |

未指定坐标时，智能体从 `(0,0)` 开始沿水平方向自动排布下一个图元。

## 目录结构

- `config.py`：TSDP / AutoCAD 路径与图层配色
- `cad_client.py`：AutoCAD COM 驱动层（在线）
- `dxf_backend.py`：离线 DXF 生成器
- `nlu.py`：中文自然语言理解（规则 + 正则）
- `agent.py`：意图调度、后端选择与默认参数
- `cli.py`：交互式命令行入口
- `demo.py`：生成示例图纸

## 说明

- 在线模式需要智能体与 AutoCAD 在同一用户会话中运行（建议在管理员 PowerShell 中运行）。
- 首次启动探索者可能弹出 UAC 提示，请允许。
- 默认保存目录为 `D:\TSSDWORK`；若不存在则保存到当前目录。
- 离线模式下“尺寸标注”会简化为标注线 + 距离文字，在线模式为真实尺寸标注。
