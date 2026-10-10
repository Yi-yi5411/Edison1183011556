# -*- coding: utf-8 -*-
"""项目名称 + 三级树结构 + 汇总表头定义。

三级树结构 DETECTION_DATA 不再硬编码，改由各检测项目插件聚合生成：
每个插件（modules/<name>/plugin.py）通过 ``structure_type``（结构类型）、
``tree_order``（同类内排序）与 ``tree_entries()``（{项目名: [构件, ...]}）
声明自己的树目录，``core.plugin_manager`` 按 混凝土结构 → 钢结构 →
木结构 → 其他 的顺序聚合，框架层无需感知具体检测项目。

新增钢结构/木结构等检测项目时，只需在 ``modules/`` 下新建插件包，
左侧勾选树即自动出现对应条目，主框架代码零改动。
"""
from core.plugin_manager import get_plugin_manager

PROJECT_NAME = '新建租赁住房项目（凌空之翼·青年社区）1#楼'

# === 三级树结构（{类别: {项目名: [构件, ...]}}，由插件聚合生成）===
DETECTION_DATA = get_plugin_manager().aggregated_detection_data()

# === SUMMARY_HEADERS ===
SUMMARY_HEADERS = ['项目名称', '检测类别', '检测项目', '构件类别', '检测结果', '备注']
