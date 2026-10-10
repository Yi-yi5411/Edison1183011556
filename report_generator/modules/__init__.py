# -*- coding: utf-8 -*-
"""检测项目模块化包。

每个子包为一个检测项目，提供 ``columns.py`` / ``calc_rules.py`` 数据字典与
``plugin.py`` 插件入口（继承 ``modules.base_plugin.BaseDetectionPlugin``）。
``core.plugin_manager`` 会在启动时动态发现并注册各插件。

聚合后的 ITEM_COLUMNS / ITEM_COLUMN_TYPES / CALC_RULES 由
``models.columns`` / ``models.calc_rules`` 经 plugin_manager 提供，
本包不再在此处硬编码聚合，以避免与插件发现过程的循环导入。

各子包：
  - concrete_strength: 混凝土抗压强度检测（回弹法/钻芯法/修正法）
  - steel_rebar:       钢筋配置（间距/根数）
  - concrete_members:  混凝土构件（厚度/尺寸）
  - cover_thickness:   保护层厚度检测（10测点）
  - anchor_bearing:    化学植筋锚固承载力检测
  - carbonation:       碳化深度
  - steel_strength:    钢结构钢材强度检测（硬度法）
  - steel_coating:     钢结构涂层厚度检测（防腐/防火）
  - steel_weld:        钢结构焊缝质量检测（超声波探伤）
  - steel_bolt:        钢结构高强度螺栓连接副检测（扭矩系数）
  - wood_moisture:     木结构木材含水率检测
  - wood_dimension:    木结构构件尺寸偏差检测
  - wood_defect:       木结构构件缺陷检测
  - wood_deflection:   木结构构件挠度检测
  - mortar_strength:   砖混结构砌筑砂浆强度检测（贯入法）
  - brick_strength:    砖混结构砖强度检测（回弹法）
  - masonry_dimension: 砖混结构砌体构件尺寸偏差检测
"""
