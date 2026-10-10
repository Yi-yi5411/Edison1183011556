# 主体结构检测数据管理录入系统V1.0

> 一款专业的建筑结构检测数据管理与报告生成工具，基于 **PyQt5** 提供 Excel 风格的数据编辑体验，采用 **五层分离 + 插件化** 架构，新增检测项目无需修改主框架代码。

---

## 目录

- [项目概述](#项目概述)
- [功能特性](#功能特性)
- [系统架构](#系统架构)
- [功能模块详解](#功能模块详解)
- [内置插件一览](#内置插件一览)
- [自动计算规则](#自动计算规则)
- [快速开始](#快速开始)
- [快捷键说明](#快捷键说明)
- [扩展开发：插件化指南](#扩展开发插件化指南)
- [项目结构](#项目结构)
- [更新说明](#更新说明)

---

## 项目概述

本系统是为建筑工程主体结构检测业务量身定制的数据管理与报告生成工具，核心设计目标：**高内聚低耦合**、**零冗余瘦身**、**插件化扩展**。

1. **可视化项目选择**：通过三级树形复选框（检测类别 → 检测项目 → 构件类别）勾选检测项
2. **Excel 风格编辑**：基于 QTableWidget 的类 Excel 网格，支持公式计算、复制粘贴、合并单元格、格式刷
3. **自动计算引擎**：根据预设规则自动计算平均值、偏差值、合格点率，钻芯法专属截面积/强度/推定值自动推算
4. **多 Sheet 导出**：一键导出为标准 Excel 格式，每个检测项目/构件对应独立工作表，保留合并单元格与样式
5. **插件化扩展**：新增检测项目只需在 `modules/` 下新建一个插件类，主框架自动发现注册，无需改一行主代码

---

## 功能特性

### 📊 核心功能

| 功能 | 描述 |
|------|------|
| **树形项目选择** | 三级联动（检测类别 → 检测项目 → 构件），支持全选/全不选/搜索过滤 |
| **Excel 风格网格** | 行号显示、列宽自适应、双击/Enter/F2 进入编辑、交替行背景 |
| **公式引擎** | 支持 Excel 风格公式（SUM、AVERAGE、IF、ROUND 等 20+ 函数） |
| **自动计算引擎** | 平均值、偏差值、合格点率 5 种计算类型，单元格变更实时重算 |
| **合并单元格** | 基于 setSpan 的可视化合并，钻芯法表格自动合并楼栋/构件/直径/推定值等列 |
| **格式刷** | 选中格式一键应用到目标区域（粗体/对齐/背景/边框等） |
| **多工作表管理** | 每个检测项目+构件独立工作表，底部标签页切换 |
| **Excel 导出** | 多 Sheet 导出，带标题、表头样式、冻结窗格、合并单元格还原 |
| **项目保存/加载** | 序列化当前所有表格数据、合并信息、格式设置，下次打开一键还原 |
| **撤销/重做** | Ctrl+Z / Ctrl+Y，最多 100 步操作历史（跨 Tab 切换不丢失） |
| **剪贴板操作** | 复制(Ctrl+C)、粘贴(Ctrl+V)、剪切(Ctrl+X)、向下填充(Ctrl+D) |
| **右键菜单** | 40+ 上下文操作（插入行/删除行/批量操作/查找替换/快速汇总等） |

### 🎨 用户体验

- **专业界面**：Microsoft YaHei 字体，蓝色主题配色（#4472C4 表头）
- **响应式布局**：QSplitter 左右分栏，支持任意比例缩放
- **状态提示**：底部状态栏实时显示操作结果、插件加载数、选中单元格统计
- **参数对话框**：钻芯法等特殊检测项勾选时自动弹出参数输入（楼栋/构件数/芯样数量等）

---

## 系统架构

### 设计原则

| 原则 | 具体含义 |
|:-----|:---------|
| **高内聚低耦合** | 界面只负责展示和交互，业务逻辑只负责计算，数据层只负责存储，互不越界 |
| **零冗余瘦身** | 清除僵尸工具函数、冗余UI事件、硬编码魔数、废弃序列化逻辑，代码量较重构前减少 30%+ |
| **插件化扩展** | 新增检测项目无需修改主框架代码，只需在 `modules/` 目录添加插件类，启动时自动发现 |

### 五层分离 + 插件化架构图

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                              应用层（入口）                                   │
│                          main.py  →  启动 Qt 事件循环                        │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│   ════════════════════════  framework/（框架核心，不轻易改动） ═══════════════│
│                                                                              │
│  ┌────────────────────────────────────┐    ┌──────────────────────────────┐  │
│  │  framework/ui/（界面层，纯展示）    │    │  framework/engine/（引擎层）  │  │
│  │                                    │    │                              │  │
│  │  main_window.py   主窗口骨架        │    │  auto_calc.py   自动计算引擎  │  │
│  │  table_widget.py  Excel 网格组件    │    │  formula.py     公式解析器   │  │
│  │  dialogs.py       通用对话框        │    │  core_drilling.py 钻芯法引擎 │  │
│  │  constants.py     UI 常量           │    │   (20+函数，纯算法无 GUI)    │  │
│  │  handlers/        UI 操作 Mixin     │    │                              │  │
│  │    ├ clipboard.py  剪贴板           │    └──────────────────────────────┘  │
│  │    ├ format.py     格式/格式刷      │    ┌──────────────────────────────┐  │
│  │    ├ merge_ops.py  合并单元格       │    │  framework/models/（数据模型）│  │
│  │    ├ row_ops.py    行增删           │    │                              │  │
│  │    ├ selection.py  选区处理         │    │  detection_data.py            │  │
│  │    ├ undo_redo.py  撤销/重做栈      │    │   · PROJECT_NAME 默认项目名   │  │
│  │    ├ edit_tools.py 查找替换/汇总    │    │   · DETECTION_DATA 三级树     │  │
│  │    └ ...                            │    │   · ITEM_COLUMNS 列定义       │  │
│  └────────────────────────────────────┘    │   · CALC_RULES 计算规则        │  │
│                                            └──────────────────────────────┘  │
│                                                                              │
│   ══════════════════════════════  core/（应用核心） ═════════════════════════│
│                                                                              │
│  ┌───────────────────────────────────────────────────────────────────────┐  │
│  │  app_controller.py   MVC 控制器：监听UI事件，编排插件/引擎/数据        │  │
│  │    · 工作表键解析（make_sheet_key / parse_sheet_key）                 │  │
│  │    · 列头查询 / 导出列映射构建                                        │  │
│  │    · 项目序列化/反序列化（保存/加载 .json）                            │  │
│  │    · 插件能力判定（requires_setup_dialog 等）                          │  │
│  ├───────────────────────────────────────────────────────────────────────┤  │
│  │  plugin_manager.py   插件加载器：启动时扫描 modules/ 动态注册          │  │
│  │    · discover() 递归扫描子包 → 发现 plugin.py → 实例化注册            │  │
│  │    · get_plugin_for_item() 按检测项名反查所属插件                     │  │
│  ├───────────────────────────────────────────────────────────────────────┤  │
│  │  event_bus.py        事件总线：发布/订阅，解耦 UI 与业务              │  │
│  │    · subscribe / unsubscribe / emit                                  │  │
│  │    · 事件：export.done / project.saved / project.loaded 等           │  │
│  └───────────────────────────────────────────────────────────────────────┘  │
│                                                                              │
│   ════════════════════════════  modules/（业务插件，可热插拔） ══════════════│
│                                                                              │
│              base_plugin.py  ←  抽象基类（统一接口：columns / calc_rules...）│
│                     ▲                                                        │
│         ┌───────────┼────────────┬─────────────┬─────────────┐              │
│         ▼           ▼            ▼             ▼             ▼              │
│  concrete_strength  steel_rebar  concrete_  cover_  anchor_   carbonation   │
│  混凝土抗压强度      钢筋配置     members     thickness  bearing   碳化深度    │
│  ├ plugin.py 插件类  ├ plugin.py  混凝土构件   保护层厚度  植筋锚固   插件    │
│  ├ columns.py 列定义  └ columns/calc_rules    └ 同上  └ 同上  └ 同上        │
│  ├ calc_rules.py                                                                         │
│  ├ handlers.py 钻芯法 GUI Mixin（仅该项目需要）                                        │
│  └ batch_assessment.py 批量评定                                                         │
│                                                                              │
│   ══════════════════════════════  utils/（通用工具） ════════════════════════│
│                                                                              │
│                      excel_exporter.py  →  统一 Excel 导出引擎               │
│                         （多Sheet / 合并还原 / 冻结窗格 / 样式渲染）            │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

### 架构分层职责

| 层次 | 目录 | 职责 | 依赖规则 |
|:-----|:-----|:-----|:---------|
| **界面层** | `framework/ui/` | 纯展示+交互：主窗口、表格、对话框、UI 操作 Mixin | 只依赖 engine / models / core，不得包含业务公式 |
| **引擎层** | `framework/engine/` | 纯算法：自动计算、公式解析、钻芯法专用计算 | 无 GUI 依赖，通过回调读写数据 |
| **数据模型层** | `framework/models/` | 纯数据结构：检测项目树、列定义、计算规则、常量 | 无依赖 |
| **应用核心** | `core/` | 控制器、插件管理器、事件总线：编排 UI↔引擎↔插件 | 依赖 framework 各层，不依赖具体插件 |
| **业务插件** | `modules/` | 各检测项目专属列定义/计算规则/GUI Mixin | 只依赖 base_plugin.py 和 framework/engine |
| **通用工具** | `utils/` | 导出、日志等跨层通用能力 | 无依赖或轻依赖 |

**依赖方向**：`main → ui → core → engine/models ← modules`，**禁止反向依赖**（如 core 不得 import 具体 modules/*）。

---

## 功能模块详解

### 1. 入口模块（`main.py`）

```python
# 功能：初始化 sys.path（注入 libs/ 供 openpyxl），启动主应用
from framework.ui.main_window import ReportGeneratorApp

app = ReportGeneratorApp()
app.run()   # 进入 Qt 事件循环
```

### 2. 界面层（`framework/ui/`）

#### 2.1 主窗口 `main_window.py` — `ReportGeneratorApp`

核心应用类，采用 **Mixin 组合模式** 组装各 UI 能力：

```python
class ReportGeneratorApp(
    CoreDrillingMixin,     # 钻芯法专属：参数对话框/自动合并/重算
    MergeOpsMixin,         # 合并单元格：Ctrl+M / Ctrl+Shift+M
    SelectionMixin,        # 选区解析：_get_sel_rows / _get_sel_cols
    FormatMixin,           # 样式：粗体/对齐/颜色/格式刷
    ClipboardMixin,        # 剪贴板：复制/粘贴/剪切/填充
    UndoRedoMixin,         # 撤销重做：100 步历史栈
    RowOpsMixin,           # 行操作：插入/删除/批量增删
    EditToolsMixin,        # 编辑工具：查找替换/快速汇总
):
    def __init__(self):
        self.controller = AppController()        # 控制器（业务逻辑）
        self._calc_engine = CalcEngine(...)      # 自动计算引擎
        self._formula_engine = FormulaEngine(...) # 公式解析器
```

- **界面布局**：QToolBar 工具栏 + QSplitter(左 QTreeWidget 右 QTabWidget+QTableWidget) + QStatusBar
- **树形面板**：根据 `DETECTION_DATA` 动态生成三级节点；勾选子检测项 → 触发 `_on_tree_item_changed` → 查询插件 `requires_setup_dialog` → 如钻芯法则弹出参数对话框 → 创建 sheet
- **工作表切换**：底部 QTabWidget，切 tab 时保存当前 sheet 的 `_merges`、`_displayed_merges`、撤销栈，并加载下一个 sheet 的数据与合并

#### 2.2 表格组件 `table_widget.py` — `MergeTableWidget`

基于 `QTableWidget` 二次封装的 Excel 风格网格：

- 重写 `mouseMoveEvent`：**移除 setCurrentCell 调用**，避免合并后选区收缩
- 自定义 ContextMenuEvent：统一生成右键菜单（40+ 操作项）
- `setSpanSafe(r, c, rs, cs)`：越界检查版合并，防止超出当前列/行范围
- 默认列数 26、行数 100（`DEFAULT_ROWS`），列宽 90px

#### 2.3 UI 常量 `constants.py`

```python
DEFAULT_ROWS = 100          # 默认表格行数
DEFAULT_COLS = 26           # 默认列数
COLUMN_WIDTH = 90           # 默认列宽
ROLE_FORMULA = Qt.UserRole + 1  # QTableWidgetItem 存储公式的 Data role
```

#### 2.4 UI 操作 Mixin（`handlers/`）

| 文件 | 核心职责 | 关键方法 |
|:-----|:---------|:---------|
| `clipboard.py` | 复制/粘贴/剪切/填充 | `_copy`, `_paste`, `_fill_down(Ctrl+D)` |
| `format.py` | 单元格样式、格式刷 | `_toggle_bold`, `_set_bg_color`, `_format_painter` |
| `merge_ops.py` | 合并/取消合并 | `_merge_cells(Ctrl+M)`, `_unmerge_all` |
| `row_ops.py` | 行增删/批量插入 | `_insert_rows`, `_delete_rows(Ctrl+Shift+D)` |
| `selection.py` | 选区解析 | `_get_sel_rows()`, `_get_sel_cols()`（兼容拖拽选区 vs 表头选区） |
| `undo_redo.py` | 撤销/重做栈 | `_push_undo()`, `_undo(Ctrl+Z)`, `_redo(Ctrl+Y)`（切 tab 保留） |
| `edit_tools.py` | 查找替换/快速汇总 | `_find_replace_dialog`, `_quick_summary` |

> **设计决策**：使用 Mixin 而非继承链的原因：每个 Mixin 只依赖主窗口暴露的公共属性（`self.table`, `self.sheet_data`, `self._merges`），互不耦合，可按需裁剪/新增。

### 3. 引擎层（`framework/engine/`）

#### 3.1 自动计算引擎 `auto_calc.py` — `CalcEngine`

**无 GUI 依赖**，通过构造时注入的 `get_cell_func(row, col)` 与 `set_cell_func(row, col, val)` 回调读写数据，可在任意宿主（Qt / CLI / 单元测试）中复用。

支持 5 种计算类型：

| 类型 | 说明 | 命名常量阈值 |
|:-----|:-----|:-------------|
| `avg` | 取源列算术平均 | — |
| `deviation` | 单源列 − 设计值列 | — |
| `pass_rate_spacing` | 钢筋间距合格点率 | `PASS_RATE_THRESHOLD_SPACING = 5.0` |
| `pass_rate_thickness` | 构件厚度合格点率 | `PASS_RATE_THRESHOLD_THICKNESS = 3.0` |
| `pass_rate_cover` | 保护层厚度合格点率 | `PASS_RATE_THRESHOLD_COVER = 3.0` |

触发时机：`main_window` 的 `cellChanged` 信号 → `_apply_calc_rules(row)` → `CalcEngine.apply_calc_rules(...)`。

#### 3.2 公式引擎 `formula.py` — `FormulaEngine`

Excel 风格公式解析器，基于 Tokenizer + 递归下降：

- 单元格引用：`A1`、`$A$1`、区域 `A1:B3`
- 运算符：`+ − * / ^`、比较符 `> < >= <= = <>`、括号
- 20+ 内置函数：见 [公式引擎支持函数](#公式引擎支持的-excel-函数)

#### 3.3 钻芯法专用引擎 `core_drilling.py`

钻芯法检测的纯算法计算（截面积 / 测试强度 / 推定值）：

```python
# 命名常量
LOAD_TO_STRENGTH_FACTOR = 1000.0   # 测试强度(MPa) = 荷载(kN) × 1000 / 截面积(mm²)
```

### 4. 数据模型层（`framework/models/detection_data.py`）

| 常量 | 类型 | 说明 |
|:-----|:-----|:-----|
| `PROJECT_NAME` | `str` | 默认项目名：新建租赁住房项目（凌空之翼·青年社区）1#楼 |
| `DETECTION_DATA` | `dict[类别, dict[子项, list[构件]]]` | 6 大类 21 子项的三级树定义 |
| `ITEM_COLUMNS` | `dict[子项, list[str]]` | 每个子项的 Excel 表头列名（与模板库严格一致） |
| `CALC_RULES` | `dict[子项, dict[col_idx, rule]]` | 衍生列自动计算规则 |
| `ITEM_COLUMN_TYPES` | `dict[子项, list[type_str]]` | 列数据类型 `string` / `float` |
| `SUMMARY_HEADERS` | `list[str]` | 汇总表表头 |

### 5. 应用核心（`core/`）

#### 5.1 控制器 `app_controller.py` — `AppController`

MVC 中的 Controller，**零 GUI 依赖**，承担所有业务编排：

| 能力 | 方法 |
|:-----|:-----|
| 插件查询 | `get_plugin_for_item(item_name)` → 委托 PluginManager |
| 工作表键 | `make_sheet_key(item, comp)`, `parse_sheet_key(key)` → `(base, comp\|None)` |
| 列定义查询 | `get_columns(sheet_key)` → 列头列表 |
| 导出列映射 | `build_export_columns(sheet_data)` → `{sheet_key: [cols]}` |
| 能力判定 | `requires_setup_dialog(item_name)` → 替代 UI 中的硬编码字符串判断 |
| 序列化 | `serialize(...)` → 可 JSON 化字典（数据+合并+格式+钻芯参数） |
| 反序列化 | `deserialize(saved)` → 六元组，恢复完整项目状态 |

#### 5.2 插件管理器 `plugin_manager.py` — `PluginManager`

单例模式（`get_plugin_manager()`），启动时调用 `discover("modules")`：

1. `pkgutil.iter_modules` 扫描 `modules/` 下所有子包
2. 尝试 `import modules.<pkg>.plugin`
3. 遍历模块属性，找出所有继承 `BaseDetectionPlugin` 的非抽象类
4. 实例化 → 调用 `register(plugin)` → 加入 `_by_id` / `_by_name` / `_plugins` 三索引

查询方法 `get_plugin_for_item(item_name)` 四级匹配策略：
1. 展示名精确匹配（如 `"混凝土抗压强度检测"`）
2. 去掉构件后缀（兼容 `sub（comp）` 与 `sub-comp` 两种格式）→ 按子项名匹配
3. 展示名互含模糊匹配
4. 返回 `None`

#### 5.3 事件总线 `event_bus.py` — `EventBus`

发布/订阅模式，解耦 UI 与业务：

```python
bus = get_event_bus()
bus.subscribe("export.done", lambda fp, ni, nr: print(f"导出完成：{fp}，{ni}个sheet {nr}行"))
bus.emit("export.done", "report.xlsx", 6, 120)
```

标准事件：`export.done`、`project.saved`、`project.loaded`。

### 6. 业务插件（`modules/`）

详见 [内置插件一览](#内置插件一览) 与 [扩展开发](#扩展开发插件化指南)。

### 7. 通用工具（`utils/`）

#### `excel_exporter.py` — `generate_excel(...)`

统一 Excel 导出入口：

```python
generate_excel(
    project_name,           # str：项目名称（写入标题行）
    sheet_data,             # dict：{sheet_key: [[cell_val, ...], ...]}
    columns_dict,           # dict：{sheet_key: [列头, ...]}
    output_path,            # str：输出文件路径
    cell_formats=None,      # dict：单元格样式
    merge_formats=None,     # dict：合并单元格样式
)
```

能力：
- 多 Sheet 生成，标题行合并居中
- 表头蓝色背景（#4472C4）白色字体
- 交替行背景（#D9E2F3）
- 边框渲染、冻结窗格（表头行）
- 合并单元格还原（根据 `_merges`）
- 导出日期自动注入

---

## 内置插件一览

| 插件 ID | 展示名 | 子检测项数 | 专属 GUI Mixin | 参数对话框 |
|:--------|:-------|:-----------|:---------------|:-----------|
| `concrete_strength` | 混凝土抗压强度检测 | 4（回弹法/高强/钻芯法/回弹钻芯修正法） | ✅ CoreDrillingMixin | ✅ 钻芯法 |
| `steel_rebar` | 钢筋配置 | 5（剪力墙间距/现浇板间距/梁根数/柱根数/墙根数） | — | — |
| `concrete_members` | 混凝土构件 | 4（楼板厚/剪力墙厚/梁尺寸/柱尺寸） | — | — |
| `cover_thickness` | 保护层厚度检测 | 4（梁/柱/剪力墙/板，各 12 测点） | — | — |
| `anchor_bearing` | 化学植筋锚固承载力检测 | 1（4 类构件） | — | — |
| `carbonation` | 碳化深度 | 1（4 类构件） | — | — |

> 合计：6 大类别，21 个子检测项。

---

## 自动计算规则

### 计算类型总览

| 类型 | 公式 / 判定 | 命名常量 |
|:-----|:------------|:---------|
| `avg` | `平均值 = SUM(源列) / COUNT(源列)` | — |
| `deviation` | `偏差值 = 实测值 − 设计值` | — |
| `pass_rate_spacing` | `\|偏差\| ≤ 5.0` 视为合格，`合格数/总数×100%` | `PASS_RATE_THRESHOLD_SPACING = 5.0` |
| `pass_rate_thickness` | `\|偏差\| ≤ 3.0` 视为合格 | `PASS_RATE_THRESHOLD_THICKNESS = 3.0` |
| `pass_rate_cover` | `\|偏差\| ≤ 3.0` 视为合格 | `PASS_RATE_THRESHOLD_COVER = 3.0` |
| `rebound_strength` | `f = 0.034488 × Rm^1.94 × 10^(-0.0173×d)` | JGJ/T 23-2011 测强曲线 |

### 回弹法专属自动计算（`concrete_strength/calc_rules.py`）

| 列 | 公式 |
|:---|:-----|
| 平均回弹值 | 测区1~测区10 非空测区的平均值，保留 1 位小数 |
| 强度推定值(MPa) | `0.034488 × 平均回弹值^1.94 × 10^(-0.0173 × 碳化深度)`，保留 1 位小数 |

### 钻芯法专属自动计算（`concrete_strength/handlers.py`）

| 列 | 公式 | 命名常量 |
|:---|:-----|:---------|
| 截面积(mm²) | `π × (直径/2)²` | `math.pi` |
| 测试强度(MPa) | `测试荷载(kN) × 1000 / 截面积(mm²)` | `LOAD_TO_STRENGTH_FACTOR = 1000.0` |
| 推定值(MPa) | 同一构件下所有芯样测试强度的 **最小值**，保留 2 位小数 | — |

**自动合并列**：楼栋（全表合并）、构件编号（按构件合并）、直径（按构件）、截面积（按构件）、推定值（按构件）、设计等级（全表合并）。

### 公式引擎支持的 Excel 函数

| 类别 | 函数 |
|:-----|:-----|
| **数学** | SUM、AVERAGE、MIN、MAX、COUNT、COUNTA |
| **数值** | ROUND、ABS、INT、SQRT、POWER |
| **逻辑** | IF、AND、OR、NOT |
| **文本** | CONCAT、UPPER、LOWER、TRIM、LEN、LEFT、RIGHT、MID |

---

## 快速开始

### 环境要求

- **Python**：3.8+（推荐 3.8 — 3.10，测试通过）
- **操作系统**：Windows 10 / 11
- **GUI 框架**：PyQt5（Qt 5.15+）
- **Excel 读写**：openpyxl ≥ 3.1（已内置在 `report_generator/libs/` 中，无需 pip 安装）

### 目录依赖说明

项目自带 `libs/` 目录内置 openpyxl，启动时 `main.py` 会自动注入 `sys.path`，**无需 pip 安装任何第三方包**即可运行。

如需额外安装 PyQt5（系统内没有时）：

```bash
pip install PyQt5
```

### 启动应用

```bash
cd structural_inspection
python report_generator/main.py
```

启动后会先弹出登录窗口。首次运行会自动导入 `user_mobile_1029.sql` 中的用户，
可使用「手机号 / 用户名」登录，密码默认为手机号；管理员账户为 `admin`，密码 `admin123`。

### 使用流程

1. **勾选检测项**：左侧树形面板展开 6 大类 → 勾选所需子检测项/构件（钻芯法会自动弹出参数对话框）
2. **切换工作表**：底部 Tab 切换到对应 Sheet
3. **录入数据**：直接在单元格输入，或从 Excel 复制粘贴（Ctrl+C / Ctrl+V）
4. **自动计算**：输入实测值/设计值后，衍生列（平均值/偏差/合格点率）自动刷新
5. **合并/格式**：选中区域 Ctrl+M 合并，工具栏设置粗体/对齐/颜色，格式刷一键复制格式
6. **保存项目**：菜单「文件 → 保存项目」导出 `.json`，下次可一键还原所有表格与合并
7. **导出 Excel**：Ctrl+S 或菜单「文件 → 导出 Excel」，生成多 Sheet 报告
8. **Word 转回弹 Excel**：菜单「文件 → Word 转回弹 Excel」，将省检测中心回弹记录 `.doc` 转换为恩施格式 `.xlsx`

---

## 快捷键说明

### 通用操作

| 快捷键 | 功能 |
|:-------|:-----|
| Ctrl+N | 添加新行 |
| Ctrl+S | 导出 Excel |
| Ctrl+F | 聚焦搜索框 |
| Ctrl+Q | 退出应用 |

### 编辑操作

| 快捷键 | 功能 |
|:-------|:-----|
| Enter / F2 | 进入编辑模式，Enter 保存并下移 |
| Tab / Shift+Tab | 保存并右移 / 左移 |
| Delete / Backspace | 清空选中单元格 |

### 剪贴板操作

| 快捷键 | 功能 |
|:-------|:-----|
| Ctrl+C / Ctrl+V / Ctrl+X | 复制 / 粘贴 / 剪切 |
| Ctrl+D | 向下填充（首行内容复制到下方选中行） |

### 撤销 / 重做

| 快捷键 | 功能 |
|:-------|:-----|
| Ctrl+Z | 撤销（100 步，跨 Tab 不丢失） |
| Ctrl+Y | 重做 |

### 导航操作

| 快捷键 | 功能 |
|:-------|:-----|
| ↑↓←→ | 方向键导航 |
| Ctrl+A | 全选 |
| Ctrl+Space / Shift+Space | 选择整列 / 整行 |
| PageUp / PageDown | 上下翻页 |
| Home / End | 行首 / 行尾 |
| Ctrl+Home / Ctrl+End | 表格首 / 末单元格 |

### 行操作

| 快捷键 | 功能 |
|:-------|:-----|
| Ctrl+Shift+I / Ctrl+Shift+K | 上方 / 下方插入行 |
| Ctrl+Shift+D | 删除选中行 |
| Ctrl+Shift+N | 批量插入多行（对话框） |

### 单元格操作

| 快捷键 | 功能 |
|:-------|:-----|
| Ctrl+M / Ctrl+Shift+M | 合并 / 取消合并单元格 |
| Ctrl+L | 调整行高（对话框） |
| Alt+= / Alt+Shift+A / Alt+Shift+M | 快速 SUM / AVERAGE / MAX |

### 批量操作

| 快捷键 | 功能 |
|:-------|:-----|
| Ctrl+Shift+F | 查找替换对话框 |

---

## 扩展开发：插件化指南

> **核心承诺**：新增检测项目时，**不需要修改 framework/、core/、main.py、main_window.py 的任何一行代码**。

### 步骤一：创建插件目录

在 `report_generator/modules/` 下创建新子包，例如 `modules/my_detection/`：

```
modules/
└── my_detection/
    ├── __init__.py        # 空文件即可
    ├── plugin.py          # 必选：插件类（继承 BaseDetectionPlugin）
    ├── columns.py         # 推荐：列头 + 列类型定义
    └── calc_rules.py      # 推荐：自动计算规则定义
```

### 步骤二：定义列头与规则

```python
# modules/my_detection/columns.py
COLUMNS = {
    # 子检测项名: [列头列表]
    "我的检测项目": ["序号", "构件名称", "设计值", "实测值1", "实测值2", "平均值", "偏差1", "偏差2", "合格点率", "备注"],
}

COLUMN_TYPES = {
    "我的检测项目": ["int", "string", "float", "float", "float", "float", "float", "float", "string", "string"],
}
```

```python
# modules/my_detection/calc_rules.py
CALC_RULES = {
    "我的检测项目": {
        # 目标列索引(从0开始): {计算类型, 源列索引列表}
        5: {"type": "avg", "sources": [3, 4]},                 # 平均值 = AVG(实测值1, 实测值2)
        6: {"type": "deviation", "source": 3, "design": 2},    # 偏差1 = 实测值1 − 设计值
        7: {"type": "deviation", "source": 4, "design": 2},    # 偏差2 = 实测值2 − 设计值
        8: {"type": "pass_rate_spacing", "sources": [6, 7]},   # 合格点率 = |偏差| ≤ 5.0 的比例
    },
}
```

### 步骤三：实现插件类

```python
# modules/my_detection/plugin.py
from modules.base_plugin import BaseDetectionPlugin
from .columns import COLUMNS, COLUMN_TYPES
from .calc_rules import CALC_RULES


class MyDetectionPlugin(BaseDetectionPlugin):
    """插件必须实现 plugin_id 和 display_name 两个属性。"""

    # ── 必须：唯一标识 + 展示名 ──
    @property
    def plugin_id(self):
        return "my_detection"    # 全项目唯一，英文蛇形命名

    @property
    def display_name(self):
        return "我的检测类别"    # 与 DETECTION_DATA 顶层键一致，树形菜单显示

    # ── 必须：列头 / 列类型 / 计算规则 ──
    def columns(self):
        return COLUMNS

    def column_types(self):
        return COLUMN_TYPES

    def calc_rules(self):
        return CALC_RULES

    # ── 以下全部可选，按需覆盖 ──

    def get_gui_mixins(self):
        """如果该检测项目需要专属 GUI 逻辑（如钻芯法的自动合并/参数对话框），
        返回需混入主窗口的 Mixin 类列表（默认空）。"""
        return []

    def requires_setup_dialog(self, sub_item):
        """勾选该子项时是否需要先弹出参数输入对话框（默认 False）。
        返回 True 时，主框架会调用该插件提供的 GUI Mixin 中的参数对话框方法。"""
        return False

    def calculate(self, worksheet_data):
        """项目专属的批量计算逻辑（无 GUI 依赖），返回结果 dict。
        worksheet_data 格式同 sheet_data: [[行数据], [行数据], ...]"""
        return {}

    def validate(self, row_data):
        """校验单行输入数据，返回 (ok: bool, message: str)。"""
        return True, ""

    def summary(self, worksheet_data):
        """生成该工作表的汇总信息（用于报告头部），返回 dict。"""
        return {}
```

### 步骤四：注册到三级树（可选：已有类别无需操作）

如果你的检测项属于 **6 大现有类别之一**，直接在 `framework/models/detection_data.py` 的对应类别下追加子项即可：

```python
# framework/models/detection_data.py → DETECTION_DATA
DETECTION_DATA = {
    # ... 现有类别 ...
    "我的检测类别": {                  # ← 新增类别名（匹配插件 display_name）
        "我的检测项目": ["梁", "柱"],  # ← 子项名 + 构件列表（空列表=不区分构件）
    },
}
```

**完成！** 重新启动应用 → 树形菜单自动出现新类别 → 勾选后 Sheet 自动生成正确列头 → 自动计算规则自动生效。

### 插件发现原理

1. `core.plugin_manager.PluginManager.discover("modules")` 在 `ReportGeneratorApp.__init__` 中被调用一次
2. 遍历 `modules/` 下所有子包名 → 尝试导入 `<pkg>.plugin` 模块
3. 扫描模块中所有 `BaseDetectionPlugin` 的非抽象子类 → 实例化 → 注册进三索引
4. 主窗口 `_populate_tree()` 读取 `DETECTION_DATA` 生成树；勾选时通过 `get_plugin_for_item` 反查插件 → 获取列头/规则/能力

### 新增插件的常见场景

| 场景 | 需要改哪些文件 |
|:-----|:---------------|
| 新增类别下的新子项 | `modules/<new>/plugin.py` + `columns.py` + `calc_rules.py` + `DETECTION_DATA` 追加 1 行 |
| 在现有类别（如混凝土抗压）追加子项 | 改对应插件的 `columns.py` / `calc_rules.py` + `DETECTION_DATA` 的对应 dict |
| 需要参数对话框（如钻芯法） | 插件新增 `handlers.py` 定义 Mixin 类 → `get_gui_mixins` 返回 → `requires_setup_dialog` 返回 True |
| 需要批量评定算法 | 插件新增 `batch_assessment.py` → 在 Mixin 的右键菜单/按钮中调用 |

---

## 项目结构

```
structural_inspection/
├── report_generator/
│   ├── main.py                           # 应用入口
│   │
│   ├── framework/                        # ═══ 框架核心（永不轻易改动） ═══
│   │   ├── __init__.py
│   │   ├── ui/                           # 界面层（纯展示，无业务公式）
│   │   │   ├── main_window.py            #   主窗口 ReportGeneratorApp（Mixin 组合）
│   │   │   ├── table_widget.py           #   Excel 网格 MergeTableWidget
│   │   │   ├── dialogs.py                #   通用对话框（钻芯法参数/批评定/查找替换/行高）
│   │   │   ├── constants.py              #   UI 常量（DEFAULT_ROWS 等）
│   │   │   └── handlers/                 #   UI 操作 Mixin
│   │   │       ├── clipboard.py          #     复制/粘贴/填充
│   │   │       ├── format.py             #     样式/格式刷
│   │   │       ├── merge_ops.py          #     合并/取消合并
│   │   │       ├── row_ops.py            #     行增删
│   │   │       ├── selection.py          #     选区解析（_get_sel_rows/cols）
│   │   │       ├── undo_redo.py          #     撤销/重做栈
│   │   │       └── edit_tools.py         #     查找替换/快速汇总
│   │   │
│   │   ├── engine/                       # 引擎层（纯算法，无 GUI）
│   │   │   ├── auto_calc.py              #   CalcEngine：5 类自动计算 + 阈值常量
│   │   │   ├── formula.py                #   FormulaEngine：20+ Excel 公式解析
│   │   │   └── core_drilling.py          #   钻芯法专用计算（截面积/强度/推定值）
│   │   │
│   │   └── models/                       # 数据模型层（纯数据结构）
│   │       └── detection_data.py         #   PROJECT_NAME / DETECTION_DATA /
│   │                                       #   ITEM_COLUMNS / CALC_RULES / ...
│   │
│   ├── core/                             # ═══ 应用级核心 ═══
│   │   ├── app_controller.py             #   AppController：控制器（编排/序列化/导出）
│   │   ├── plugin_manager.py             #   PluginManager：插件发现注册（单例）
│   │   └── event_bus.py                  #   EventBus：发布订阅解耦
│   │
│   ├── modules/                          # ═══ 业务插件（可热插拔） ═══
│   │   ├── base_plugin.py                #   抽象基类 BaseDetectionPlugin
│   │   ├── concrete_strength/            #   1. 混凝土抗压强度检测
│   │   │   ├── plugin.py                 #      ConcreteStrengthPlugin
│   │   │   ├── columns.py                #      列头/列类型
│   │   │   ├── calc_rules.py             #      自动计算规则
│   │   │   ├── handlers.py               #      CoreDrillingMixin（钻芯法 GUI）
│   │   │   └── batch_assessment.py       #      批量评定算法
│   │   ├── steel_rebar/                  #   2. 钢筋配置
│   │   ├── concrete_members/             #   3. 混凝土构件
│   │   ├── cover_thickness/              #   4. 保护层厚度检测
│   │   ├── anchor_bearing/               #   5. 填充墙植筋锚固
│   │   └── carbonation/                  #   6. 碳化深度
│   │
│   ├── utils/                            # ═══ 通用工具 ═══
│   │   └── excel_exporter.py             #   多 Sheet Excel 导出引擎
│   │
│   └── libs/                             # 内置第三方库（openpyxl，免 pip 安装）
│       ├── openpyxl/
│       └── openpyxl-3.1.5.dist-info/
│
├── 模板库/                                # 业务模板参考（表头、格式）
│   ├── 1、混凝土抗压强度检测/
│   ├── 2、钢筋配置/
│   └── ...
├── 需求逻辑提示词/                        # 需求文档与示例数据
└── README.md                              # 本文件
```

---

## 更新说明

### v3.0.0 (2026-08-14)

**架构级重构**：五层分离 + 插件化

#### 一、代码清理（零冗余瘦身）

- 删除 `utils/cell_utils.py` 等僵尸工具函数
- 删除 `data.py`、`excel_generator.py`、`formula_engine.py` 兼容垫片
- 删除重复 QShortcut 绑定、未使用右键菜单项
- 抽取硬编码魔数为命名常量：
  - `PASS_RATE_THRESHOLD_SPACING = 5.0`
  - `PASS_RATE_THRESHOLD_THICKNESS = 3.0`
  - `PASS_RATE_THRESHOLD_COVER = 3.0`
  - `LOAD_TO_STRENGTH_FACTOR = 1000.0`

#### 二、模块化拆分（高内聚低耦合）

- **framework/ui/**：界面层（main_window / table_widget / dialogs / handlers Mixin）
- **framework/engine/**：引擎层（auto_calc 通用计算 / formula 公式 / core_drilling 钻芯法）
- **framework/models/**：数据模型层（detection_data.py 集中管理所有数据定义）
- **core/app_controller.py**：控制器，业务逻辑从 UI 完全剥离（工作表键解析/序列化/导出列映射/插件能力判定）
- **core/event_bus.py**：事件总线，发布订阅解耦 UI 与业务
- **core/plugin_manager.py**：插件管理器，启动时动态发现注册

#### 三、插件化扩展

- `modules/base_plugin.py` 定义统一接口（`columns` / `calc_rules` / `validate` / `summary` 等）
- 6 大检测项目全部插件化：`concrete_strength`、`steel_rebar`、`concrete_members`、`cover_thickness`、`anchor_bearing`、`carbonation`
- 新增检测项目只需在 `modules/` 下新建插件类，主框架零改动

#### 四、保真迁移（功能零丢失）

- 50+ 快捷键体系完整保留
- 40+ 右键菜单操作完整保留
- 合并单元格、格式刷、撤销重做（跨 Tab 保留）完整保留
- 自动计算（平均值/偏差/合格点率/钻芯法三列）完整保留
- 多 Sheet Excel 导出（含合并还原/冻结窗格/样式）完整保留
- 项目保存/加载（序列化完整状态）完整保留

---

### v2.1.0 / v2.0.0 历史更新

详见旧版 README（各快捷键、右键菜单、公式引擎、保护层 12 测点扩展、钻芯法表头更新、导出增强等）。
