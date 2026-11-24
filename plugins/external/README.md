# 外部插件目录

把外部检测项目插件放在这里（每个插件一个子目录）：

    plugins/external/<plugin_id>/
        plugin.json      # structural.item/1 manifest，必需
        plugin.py        # 可选；存在且 source=python 时加载
        helpers.py ...   # 可选；同目录模块可被 plugin.py import

## manifest 最小示例

```json
{
  "schema": "structural.item/1",
  "id": "my_detection",
  "name": "我的检测项目",
  "structure_type": "其他",
  "tree_order": 900,
  "source": "manifest",
  "items": [{
    "key": "我的检测项目",
    "components": [],
    "columns": ["构件名称", "检测值"],
    "column_types": ["string", "float"],
    "equipment": []
  }]
}
```

- `source=manifest`：纯 JSON 声明，不执行 Python 代码。
- `source=python`：需要 `plugin.py`，其中实现 `BaseDetectionPlugin` 子类；
  加载时会执行本机代码，只放可信插件。
- 保存目录后可在“插件管理”页点击“重新加载全部插件”，不用重启后端。
- 插件 id 不能与内置插件或其他外部插件重复；冲突会在加载记录里显示。
