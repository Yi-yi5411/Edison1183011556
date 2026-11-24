# CAD 与结构计算集成（P7）

两部分都是**独立 MCP 服务**：DSH 负责语义理解与编排，服务只执行结构化指令。

## 1. CAD（AutoCAD 2020 / 探索者 TSDP2024）

原 `cad_agent/` 是自带中文 NLU 的独立智能体；本项目已改为：

| 原文件 | 处理 |
|---|---|
| `nlu.py`、`agent.py` | **删除**（应用内 NLU 循环与“收敛到 DSH”冲突） |
| `cad_client.py` | 保留 COM 驱动；`pywin32` 改为延迟导入（无 pywin32 也能用 DXF） |
| `dxf_backend.py` | 保留，离线出图 |
| `config.py` | 改为读 `config/structural.toml` 的 `[cad]`，不再写死本机路径 |
| `drawing.py` | **新增**：在线/离线统一接口、参数校验、JSON 摘要、计划执行 |
| `cli.py` | 改为结构化子命令（`status` / `open` / `draw --spec`），不做 NLU |
| `mcp_server.py` | **新增**：12 个 MCP 工具 |

图纸单位统一 **毫米**。

### 工具（serverName `autocad`）

| 工具 | 说明 | 写 |
|---|---|---|
| `cad_status` | 后端（com/dxf）、文档名、工作目录、单位 | — |
| `cad_open` | 启动探索者并连接 AutoCAD | ✓ |
| `cad_grid` | 轴网 + 轴号（1..n / A..n） | ✓ |
| `cad_column` / `cad_beam` / `cad_wall` | 柱 / 梁 / 墙 | ✓ |
| `cad_rect` / `cad_circle` / `cad_text` / `cad_dimension` | 基本图元 | ✓ |
| `cad_save` | 在线存 DWG、离线写 DXF，返回路径与大小 | ✓ |
| `cad_zoom` | 缩放到图形范围 | — |

写工具必须 `confirm=true`；无 AutoCAD 时 `backend=auto` 自动回退 DXF 并给出原因。

### 配置

```toml
[cad]
backend = "auto"          # auto | com | dxf
acad_progid = "AutoCAD.Application.23"
acad_exe = "D:\\Program Files\\Autodesk\\AutoCAD 2020\\acad.exe"
tsdp_dir = "D:\\Program Files\\TszCAD\\TSDP2024"
work_dir = "D:\\TSSDWORK"
text_height = 300
axis_label_diameter = 800
```

环境变量：`STRUCTURAL_CAD_BACKEND` / `STRUCTURAL_ACAD_PROGID` / `STRUCTURAL_TSDP_DIR` 等。

### 计划（JSON）

```json
{"ops": [
  {"op": "grid", "x_bays": 3, "y_bays": 2, "x_spacing": 6000, "y_spacing": 7200},
  {"op": "column", "center": [0, 0], "width": 400},
  {"op": "beam", "p1": [0, 0], "p2": [18000, 0], "width": 300},
  {"op": "text", "text": "一层平面图", "point": [0, 9000], "height": 500},
  {"op": "save", "path": "D:/out/plan.dxf"}
]}
```

`python -m cad_agent.cli draw --spec plan.json --out out.dxf`

## 2. 结构计算（盈建科 YJK）

YJKAPI 只存在于**盈建科安装目录自带的 Python 3.10**（`C:\\YJKS\\YJKS_8_0_0\\Python310`），
主程序（3.8）不能 import 它。因此采用「生成脚本 → 子进程执行 → 读 JSON」：

```text
DSH → yjk MCP（主 Python 3.8）
        ├─ model.py   生成 YJKAPI 脚本（纯函数，可编译校验）
        └─ bridge.py  用 [yjk].python 执行脚本，解析最后一行 JSON
```

API 调用全部取自官方示例（`docs/references/yjkapi_-python-8.1/案例/二次开发/...`）：

```python
from YJKAPI import *
dataFunc = DataFunc()
StdFlr = dataFunc.StdFlr_Generate(3900)
defcol = dataFunc.ColSect_Def(6, 1, "400,400")
node = dataFunc.Joint_Generate(StdFlr.ID, x, y)
grid = dataFunc.Grid_Generate(StdFlr.ID, n1.ID, n2.ID, axis.ID)
dataFunc.column_arrange(nodelist, defcol); dataFunc.beam_arrange(gridlist, defbeam)
dataFunc.Floors_Assemb(0, StdFlr, 6, 3600); dataFunc.DbModel_Assign()
my = Hi_AddToAndReadYjk(dataFunc.GetDbModelData()); my.CreateYDB(dir, "kj.ydb")
```

### 工具（serverName `yjk`）

| 工具 | 说明 | 写/危险 |
|---|---|---|
| `yjk_status` | Python、安装目录、YJKAPI 是否可导入 | — |
| `yjk_build_frame` | JSON 规格 → 建模脚本 → `.ydb` | 写（confirm） |
| `yjk_read_ydb` | 读 `.ydb`：标准层/楼层/节点数/截面 | — |
| `yjk_run_script` | 执行项目或工作目录内脚本 | 危险（confirm + confirm_delete） |

规格示例：

```json
{
  "name": "kj",
  "floors": {"height": 3900, "number": 6, "floor_height": 3600},
  "x": [0, 3900, 7800, 11700],
  "y": [0, 6700, 12000],
  "column_sections": [{"mat": 6, "kind": 1, "shape": "400,400"}],
  "beam_sections": [{"mat": 6, "kind": 1, "shape": "250,600"}],
  "slab": {"centroid": [1950, 9350], "thick": 300, "dead_live": [9, 9]}
}
```

### 配置

```toml
[yjk]
install_dir = "C:\\YJKS\\YJKS_8_0_0"
python = "C:\\YJKS\\YJKS_8_0_0\\Python310\\python.exe"
work_dir = "data/yjk"
timeout = 900
```

## 3. 在 DSH 里启用

把下面两个片段的条目并入 profile 的 `cordis.patch.yml`：

- `cad_agent/dsh-patch.yml` → serverName `autocad`
- `integrations/yjk/dsh-patch.yml` → serverName `yjk`

`install.ps1` 会检查 AutoCAD / 探索者 / pywin32 / 盈建科 Python / YJKAPI，并打印主 MCP 片段。

## 4. 测试

- `python tests/test_cad_agent.py`（25 项）：配置、轴网/构件几何、DXF 落盘与结构、计划执行、
  参数校验、12 个工具与 confirm 门、pywin32 延迟导入。
- `python tests/test_yjk_integration.py`（21 项）：规格校验、建模脚本内容与可编译性、
  读取脚本、缺环境时的状态与报错、4 个工具与危险门。

两者都不需要安装 AutoCAD / YJK，走离线与桩验证。
