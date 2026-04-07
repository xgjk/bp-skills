## reporting 脚本索引

### 脚本清单

1. `list_periods.py`
   - 用途：列出 BP 周期，供用户选择 `periodId`
   - 鉴权：`appKey`

2. `generate_filling_guides.py`
   - 用途：按 `periodId` + 组织节点生成月报/季报/半年报/年报的“填写规范”（含审查输出）
   - 鉴权：`appKey`

### 运行时日志

如需运行日志，应写入工作区根目录 `.cms-log/`（本仓库实现阶段默认不落盘日志）。

