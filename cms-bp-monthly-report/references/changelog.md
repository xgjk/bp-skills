# BP 个人月度汇报 Skill 变更记录

> 记录每次修改遇到的问题、影响点、修复方案以及后续预防措施。

---

## v1.3 — 2026-04-23  流程改造：bp_monthly_report → bp_openclaw_task

### 变更：Skill 写接口底层从 bp_monthly_report 切换到 bp_openclaw_task

| 项目 | 说明 |
|------|------|
| **背景** | 原流程中 `save` 和 `updateStatus` 先写 `bp_monthly_report`，再联动 `bp_openclaw_task`。Skill 流程实际不需要 `bp_monthly_report` |
| **变更** | PMS 端 `saveOrUpdateMonthlyReport` 和 `updateGenerateStatus` 底层实现改为直接操作 `bp_openclaw_task`，不再写 `bp_monthly_report` |
| **接口不变** | Open 端 `/bp/monthly/report/save` 和 `/bp/monthly/report/updateStatus` 路径和参数完全不变 |
| **脚本调整** | `save_openclaw_report` 改调 `/bp/monthly/report/save`（原来调的 `/bp/monthly/report/saveOpenClawReport` 后端不存在）|
| **流程简化** | `save` 接口保存内容时自动标记任务 SUCCESS，不再需要额外调 `update_report_status --status 1`；仅失败时才需调 `update_report_status --status 2` |

---

## v1.2 — 2026-04-15  稳定性加固

### 问题 1：`_do_request` 中 headers 字典被 mutation

| 项目 | 说明 |
|------|------|
| **现象** | `_do_request` 在 POST 请求中直接修改传入的 `headers` 字典（添加 `Content-Type`），当 retry 循环复用同一 headers 时，GET 请求也会携带 `Content-Type: application/json`，虽然当前未造成实际错误，但属于隐患 |
| **影响** | retry 循环第二次请求可能携带不必要的 header，部分严格校验的服务端可能拒绝 |
| **修复** | POST 分支改为创建新 dict `req_headers = {**headers, "Content-Type": "application/json"}`，不修改原始 headers |
| **预防** | 所有构建请求 header 的地方禁止直接修改传入对象，统一用浅拷贝或新建 dict |

### 问题 2：保存月报绕过 `_request` 缺少 retry 能力

| 项目 | 说明 |
|------|------|
| **现象** | 保存月报直接 `requests.post()` 调用 API，没有经过 `_request` 包装，因此不具备 retry 和标准化错误处理 |
| **影响** | 保存月报时遇到 401/429/5xx 不会自动重试，直接失败 |
| **修复** | 改为调用 `_request("POST", "/bp/monthly/report/save", json_body=body)`，统一走 retry 逻辑 |
| **预防** | 新增 API 调用一律使用 `_request` 包装，禁止直接 `requests.get/post` |

---

## v1.1 — 2026-04-15  API 字段名修复 + 查询 retry

### 问题 1（Critical）：API 字段名不匹配

| 项目 | 说明 |
|------|------|
| **现象** | 函数硬编码使用 `keyResultList` 和 `actionList` 获取 KR 和 Action 列表，但 API 实际返回的字段名是 `keyResults` 和 `actions` |
| **影响** | 只能获取到目标本身 1 个节点的 ID，无法获取其下所有 KR 和举措节点 |
| **根因** | 开发时参考了旧版 API 文档或猜测字段名，未用实际 API 返回数据做验证 |
| **修复** | 改为兼容双字段名：`goal_detail.get("keyResultList") or goal_detail.get("keyResults") or []` |

### 问题 2：数据查询 API 缺少 retry 逻辑

| 项目 | 说明 |
|------|------|
| **现象** | `_request` 函数遇到 401/429/5xx 时直接返回错误 |
| **影响** | 数据采集阶段遇到瞬时限流或服务端错误会直接失败，需要人工重跑 |
| **修复** | 重构 `_request`：拆出 `_do_request` 执行单次请求，`_request` 添加 retry 循环，对 401/429/5xx 等待 60 秒后重试一次 |
| **预防** | 所有 API 调用统一走 `_request`，retry 策略集中管理 |

---

## v1.0 — 2026-04-13  KR 去灯色 + 2.1/2.2 合并

### 修改 1：KR 级别去掉灯色判断

| 项目 | 说明 |
|------|------|
| **变更** | 关键成果（KR）不再判灯色，只输出"判断理由"做差距分析；灯色判断仅在举措级和目标级执行 |
| **涉及文件** | `SKILL.md`（判断主轴/层级/KR卡片/合规清单）、`report-template-bp-self-check.md`（KR 明细/AI 指引）、`traffic-light-rules.md`（头部说明/灯色判断优先级） |
| **影响** | KR 卡片结构简化，四灯判断块仅在举措级和目标级出现；目标灯色从举措灯色聚合（跳过 KR） |

### 修改 2：2.1 目标清单总览与 2.2 合并

| 项目 | 说明 |
|------|------|
| **变更** | 原 2.1（参与自查目标表）和 2.2（未参与自查目标汇总）合并为统一的 2.1 目标清单总览表 |
| **影响** | 被排除的目标在合并表中用 `<span style="color:#2e7d32; font-weight:700;">★</span>` 标记灯色，结论写"未启动"，证据引用留空。原 2.3 目标明细改编号为 2.2 |
| **涉及文件** | `SKILL.md`（合规清单/报告约束）、`report-template-bp-self-check.md`（2.1/2.2/2.3 章节结构）、`traffic-light-rules.md`（排除行为描述） |

---

## 后续预防措施

### 1. API 字段兼容性

- 新增 API 调用时，先用实际数据打印字段名，再编码
- 对关键字段（列表类型）统一使用 `or` 兼容多种命名：`obj.get("fieldA") or obj.get("fieldB") or []`
- 部门月报脚本和个人月报脚本使用的字段名需同步检查

### 2. 网络调用统一

- 所有 API 调用统一通过 `_request` 包装
- 禁止在业务函数中直接 `requests.get/post`
- retry 策略集中在 `_request` 管理

### 3. 测试验证

- 修改数据采集逻辑后，必须对所有目标重新运行 `collect_goal_progress` 验证采集结果
- 对照修改前后的数据差异，确认修复效果
