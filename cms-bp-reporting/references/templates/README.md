## templates 模块说明（模板查询 / 版本管理）

### 适用场景

用于 BP 报告链路中的“空白母版模板”相关能力：

1. 查询当前有哪些模板版本
2. 获取指定版本下的某个模板文件（月报/季报/半年报/年报）
3. 更新 bp-prototype 所依赖的 BP 规范文件（从 GitHub 拉取）
4. 创建新版本目录并生成四套空白母版模板（版本化）

### 数据来源与存储

- 模板版本目录来源：`bp-prototype/versions/`
- 规范来源：GitHub `xgjk/dev-guide` 的 BP 业务说明（由 `bp-prototype` 脚本负责拉取与落盘）

### 输入最小集

- 列版本：无需参数
- 取模板文件：`--version-dir` + `--template-type`
- 更新规范：无需参数
- 生成新版本：无需参数（但要求 `bp-prototype/references/` 依赖齐全）

### 输出

- 列版本：输出版本目录清单与可用模板文件清单（JSON）
- 取模板：输出模板 Markdown 全文（stdout）
- 更新规范/生成版本：输出执行结果（stdout/stderr）

### 约束

- 本模块不调用 BP Open API，不需要 `appKey`
- 版本目录与文件一律只读列出，不做删除

