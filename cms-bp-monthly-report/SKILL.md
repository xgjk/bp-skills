---
name: cms-bp-monthly-report
description: >-
  BP个人月度汇报生成与发送工具。基于 BP 目标结构、衡量标准和当月汇报证据，
  按分步流程生成结构固定、证据可追溯的月报初稿。
  当用户需要生成、发送或预览个人BP月度汇报时使用。
skillcode: cms-bp-monthly-report
github: https://github.com/xgjk/bp-skills/tree/main/cms-bp-monthly-report
dependencies:
  - cms-auth-skills
  - bp-data-viewer
---

# BP 个人月度汇报

**当前版本**: 0.1.0  
**接口版本**: v1（BP Open API，`/open-api/bp/*`）

为 BP 系统中的个人节点生成月度汇报。核心逻辑是**先拆证据、再做判断、最后组装报告**，而不是一步生成整篇。

数据获取依赖 `bp-data-viewer` Skill，遵循其缓存优先策略（详见 [bp-data-viewer 缓存指南](../bp-data-viewer/references/cache-guide.md)）。

详细参考：
- 月报模板：[references/report-template.md](references/report-template.md)
- 灯色判断标准：[references/traffic-light-rules.md](references/traffic-light-rules.md)
- 证据优先级规则：[references/evidence-rules.md](references/evidence-rules.md)

## 核心业务概念

### 判断主轴

月报的判断主轴是 **目标 → 关键成果 → 衡量标准**，不是举措。

- **目标**：最终要达到的状态，定义"这条线在做什么"
- **关键成果**：判断目标有没有达成的核心依据
- **衡量标准**：说明关键成果怎样算完成、怎样算偏离
- **关键举措**：为实现成果而采取的动作路径，是证据抓手而非评价主轴

一句话：看"成果离衡量标准还有多远"，不是看"举措做了多少"。

### 灯色判断层级

- **判断卡片（Step 3c）**：灯色判断的最小单元是**关键成果**和**关键举措**，分别生成卡片。
- **最终报告（Step 3d）**：
  - **第 2 章**：灯色判断到**目标级**——综合该目标下所有 KR 卡片得出一个目标级灯色。
  - **第 3 章**：每个核心结果事项带灯。
  - **第 4 章**：每个关键举措单独带灯。
  - **第 5 章**：每个问题/偏差带灯。
  - **第 6 章**：每个风险带灯。
  - **第 1 章**：综述中"本月总体判断"和"对下月的总体判断"各带一个灯。
- 所有灯色判断点使用统一的**三灯判断块**格式（见 report-template.md "三灯判断块标准模板"一节）。

### 灯规则版本

支持两个版本，由用户在调用时指定：

- **版本一**（默认）：严格口径，适用于标准考核场景。
- **版本二**：放宽口径——绿灯可容忍部分节点未完成或 1-2 周滞后；黄灯只用于已对最终达成构成实质威胁的事项，但仍必须整改。

详见 [references/traffic-light-rules.md](references/traffic-light-rules.md) 的"版本二"章节。

### 证据引用编号

最终报告中引用汇报时使用 `R{序号}` 编号（如 `R201`、`R202`），不直接内联汇报正文或 reportId。编号在 Step 3b 证据台账中分配。

### 灯色 HTML 渲染

最终报告中所有灯色相关文字使用 HTML `<span>` 标签彩色加粗渲染：

| 灯色 | HTML 样式 |
|------|-----------|
| 🟢 | `<span style="color:#2e7d32; font-weight:700;">` |
| 🟡 | `<span style="color:#b26a00; font-weight:700;">` |
| 🔴 | `<span style="color:#c62828; font-weight:700;">` |
| ⚫ | `<span style="color:#212121; font-weight:700;">` |

## 生成流程

**禁止一步生成整篇报告。** 必须按以下步骤顺序执行。

### 第一步：确定目标员工与月份

用户需提供：
- **目标员工**：员工姓名、employeeId 或 groupId（个人分组 ID）
- **汇报月份**：格式 `YYYY-MM`，如 `2026-03`
- **灯规则版本**：`版本一`（默认）或 `版本二`

推荐输入协议：

```yaml
period_id: 1994002024299085826
groupId: 2029384010718834690
report_month: 2026-03
light_rule_version: 版本二
```

若用户只给了姓名，通过 `bp-data-viewer` 的 `search_group_by_name` 在个人分组中按名称匹配定位。若没有 `period_id`，用 `get_all_periods` 取 `status=1` 的启用周期。

### 第二步：采集 BP 数据与当月汇报

确定 `groupId` 和月份后，使用 `collect_monthly_data` 一次性采集全部数据：

```bash
python3 .cursor/skills/bp-monthly-report/scripts/monthly_report_api.py collect_monthly_data \
  --group_id "{groupId}" \
  --month "2026-03" \
  --output "/tmp/monthly_data_{groupId}.json"
```

该命令在脚本内部自动完成：
1. 获取该员工的 BP 任务树（目标 → 关键成果 → 关键举措）
2. 获取每个目标的完整详情（含衡量标准、参与人）
3. 遍历所有节点查询当月关联汇报列表
4. 批量拉取所有汇报正文内容（按 reportId 去重）
5. 构建反向索引（reportId → 关联的 taskId 列表）
6. 将全部数据写入一个聚合 JSON 文件

执行完成后，直接 **Read** 输出的 JSON 文件即可获取全部数据。

**输出 JSON 结构**：

| 字段 | 说明 |
|------|------|
| `taskTree` | 精简后的任务树（目标 → 关键成果 → 关键举措） |
| `goalDetails` | 各目标的完整详情（key 为 goalId） |
| `uniqueReportMap` | reportId → 完整汇报内容的去重主表 |
| `reportTaskMapping` | reportId → 关联的 taskId 列表（反向索引） |
| `reports` | 按 taskId 分组的汇报引用（兼容旧结构） |
| `stats` | 统计信息：总任务数、目标数、去重汇报数等 |
| `errors` | 采集过程中的错误记录（如有） |

**注意**：单条汇报内容超过 2000 字会被截断并标注 `[...truncated]`。

### 第三步：生成月报内容（分 4 个子步骤）

读取采集数据后，**必须按以下 4 个子步骤顺序执行**，不可跳步。

#### Step 3a: 构建 BP 锚点图

从 `goalDetails` 中提取每个目标的结构化骨架：

对每个目标，提取：
- 目标名称、编号（fullLevelNumber）
- 上级组织 BP 对齐关系（upwardTaskList）
- 下属关键成果列表，每个关键成果提取：
  - 名称、编号
  - **衡量标准**（measureStandard，去除 HTML 标签）
  - 监督人、承接人
  - 计划时间范围（planDateRange）
  - 当前状态（statusDesc）
- 下属关键举措列表，每个举措提取：
  - 名称、编号
  - 计划时间范围（planDateRange）
  - 当前状态（statusDesc）

将此骨架写入 `/tmp/bp_anchor_{groupId}.md`，作为后续判断的锚点。

#### Step 3b: 构建证据台账（含 R 编号分配）

对采集到的汇报数据，严格按 [references/evidence-rules.md](references/evidence-rules.md) 执行：

1. **按 reportId 去重**：使用 `uniqueReportMap`，同一条汇报关联到多个节点只算一次
2. **内容聚合**：内容高度相似的汇报（同一模板发给不同人）合并为一个工作事项，记录发送次数和对象列表
3. **证据分级**：
   - 本人手动汇报（type=manual，作者是承接人本人）→ 主证据
   - 他人手动汇报（type=manual，作者非本人）→ 辅证
   - AI 汇报（type=ai）→ 仅辅助摘要，不能单独作为强结论依据
4. **分配 R 编号**：对去重聚合后的每个独立工作事项，按顺序分配 `R{月份}{序号}` 编号。例如 3 月月报的第 1 条证据编号为 `R301`，第 2 条为 `R302`；1 月月报为 `R101`、`R102`。编号规则：
   - 月份取汇报月份的数字（1月=1，12月=12）
   - 序号从 01 开始连续递增
   - 每条编号附带汇报标题全文，格式：`R{编号}`《[汇报标题]》
5. **按节点归集**：利用 `reportTaskMapping` 确定每条汇报关联了哪些目标/关键成果/关键举措。一条汇报的内容如果明确涉及其他目标的关键词，应在对应节点的分析中交叉引用
6. **月份归集口径**：以汇报的 `createTime` 为准，不依赖关联时间或正文时间推断

将证据台账写入 `/tmp/evidence_ledger_{groupId}.md`，格式为：

```markdown
## 证据台账

### R 编号索引
- `R301`《[汇报标题]》— 主证据，关联节点：目标X/KRY
- `R302`《[汇报标题]》— 辅证，关联节点：举措Z
- ...

### 统计摘要
- 命中原始工作汇报：N 份
- 经批量通知归并后最终采纳：M 份
- 其中本人主证据：X 份、他人手动汇报：Y 份、AI 汇报：Z 份

### 按目标归集
#### 目标: [目标名称]
- 主证据：`R301`、`R303`
- 辅证：`R302`
- 无证据的 KR/举措：[列表]

### 按关键举措归集
#### Action: [举措名称]
- 主证据：[列表]
- 辅证：[列表]
- 无证据：是/否
```

#### Step 3c: 生成判断卡片

对每个关键成果和每个关键举措，分别生成一张判断卡片。严格按 [references/traffic-light-rules.md](references/traffic-light-rules.md) 判断灯色（根据用户指定的灯规则版本）。

**关键成果卡**（每个关键成果一张）：

```markdown
### KR卡: [关键成果名称] ([编号])

- 衡量标准：[从 measureStandard 提取]
- 计划时间范围：[planDateRange]
- 当月是否在计划期内：是/否
- 本月主证据：[R编号列表]
- 本月辅证：[R编号列表]
- 距离衡量标准的差距：[基于证据判断]
- 灯色判断：[🟢/🟡/🔴/⚫/--]
- 判断依据：[说明为什么是这个灯色]
```

若灯色为 🟡/🔴/⚫，必须追加：

```markdown
- 偏差/问题描述：
- 整改方案建议：
- 建议承诺完成时间：
- 下周期具体举措：
```

若灯色为 ⚫，还必须追加：

```markdown
- 黑灯类型建议（需人工复核）：[未开展/已开展但未关联/体外开展无留痕]
- 类型判断依据：
```

**关键举措卡**（每个关键举措一张）：

```markdown
### Action卡: [举措名称] ([编号])

- 计划时间范围：[planDateRange]
- 当月是否在计划期内：是/否
- 当前状态：[statusDesc]
- 本月推进动作：[从证据提取，引用R编号]
- 对关键成果的支撑情况：[说明支撑了哪个 KR，强/中/弱]
- 灯色判断：[🟢/🟡/🔴/⚫/--]
- 判断依据：
```

将所有卡片写入 `/tmp/judgment_cards_{groupId}.md`。

#### Step 3d: 组装最终报告

基于判断卡片和证据台账，按 [references/report-template.md](references/report-template.md) 逐章组装。

**组装顺序**（第 1 章放到最后写，但最终文件中排第 1 章）：

1. **元数据头**：填入周期名称、员工姓名、基线、口径说明、灯规则版本等
2. **第 2 章 BP目标承接与对齐**：
   - 按目标遍历，每个目标一个 `### 2.x` 小节
   - 每个目标包含：对标BP、关键成果（KR摘要）、关键举措抓手（举措摘要）、本月承接重点、当前状态（叙事 + R编号证据引用）
   - **目标级灯色**：综合该目标下所有 KR 卡片的灯色得出。规则：有任一红灯则目标红灯；无红灯但有黄灯则目标黄灯；全绿则目标绿灯；全黑灯则目标黑灯。-- 不参与汇总。
   - 每个目标末尾嵌入**三灯判断块**
3. **第 3 章 核心结果与经营表现**：
   - 每个事项包含：对应目标、对应成果、本月结果（叙事）、结果判断
   - 每个事项末尾嵌入**三灯判断块**
4. **第 4 章 关键举措推进情况**：
   - 每条举措包含：对应举措名、推进动作、支撑强度、当前进度
   - 每条举措末尾嵌入**三灯判断块**
5. **第 5 章 问题、偏差与原因分析**：
   - 从 🟡/🔴/⚫ 卡片中提取，每个问题包含：对应BP、当前问题、原因分析、影响
   - 每个问题末尾嵌入**三灯判断块**
   - 若全部为 🟢 或 --，写"本期无重大偏差"
6. **第 6 章 风险预警与资源需求**：
   - 每个风险包含：对应BP、风险内容、当前应对、所需支持
   - 每个风险末尾嵌入**三灯判断块**
7. **第 7 章 下月重点安排**：精简 bullet list，4-5 条要点
8. **第 8 章 需决策/需协同事项**：需拍板事项、需协调事项、需要支持事项
9. **第 1 章 汇报综述**（最后写，但在文件中排第一）：
   - 参考工作汇报数（三层口径，从证据台账统计摘要获取）
   - 本月总体判断（叙事 + 三灯判断块）
   - 本月最关键的进展（要点 + R编号证据引用）
   - 本月最需要关注的问题
   - 对下月的总体判断（叙事 + 三灯判断块）

**三灯判断块渲染规则**：
- 灯色文字全部使用 HTML `<span>` 标签渲染（色值见 report-template.md 色值表）
- 绿灯判断块：灯色 + 判断理由（共 2 行，不需要人工确认入口）
- 黄灯/红灯/黑灯判断块：灯色 + 判断理由 + 人工判断待确认 + 若同意 + 若不同意 + 整改方案 + 承诺完成时间 + 下周期具体举措（共 8 行）
- 黑灯判断块：在上述基础上再追加黑灯类型建议（共 9 行）

**最终文件章节排列**：1 → 2 → 3 → 4 → 5 → 6 → 7 → 8

将最终报告写入 `/tmp/monthly_report_{groupId}.md`。

### 第四步：展示与发送

生成完成后，**必须先将完整月报展示给用户确认**，用户确认后再发送。

```bash
python3 .cursor/skills/bp-monthly-report/scripts/monthly_report_api.py send_report \
  --receiver_emp_id "{employeeId}" \
  --title "{YYYY-MM} 个人BP月度汇报" \
  --content_file "/tmp/monthly_report_{groupId}.md" \
  --sender_id "400002"
```

**发送参数说明**：
- `--receiver_emp_id`：接收人，即员工本人的 employeeId（从分组的 employeeId 字段获取）
- `--title`：汇报标题，格式 `{YYYY-MM} 个人BP月度汇报`
- `--content_file`：月报内容文件路径（Markdown）
- `--sender_id`：发送人 ID，默认 `400002`（BP 系统虚拟用户）

**发送完成后，必须保存月报到 BP 系统**（2.22 saveMonthlyReport）：

```bash
python3 .cursor/skills/bp-monthly-report/scripts/monthly_report_api.py save_monthly_report \
  --group_id "{groupId}" \
  --month "{YYYY-MM}" \
  --content_file "/tmp/monthly_report_{groupId}.md"
```

**保存参数说明**：
- `--group_id`：员工个人分组 ID
- `--month`：汇报月份，格式 `YYYY-MM`
- `--content_file`：月报内容文件路径（同发送时使用的文件）
- 使用 **数据查询 key**（`BP_OPEN_API_APP_KEY`）调用，机器人 key 无权限

## 工具脚本

### bp-data-viewer（数据底座，已有）

所有 BP 数据查询通过 `bp-data-viewer` 的 `bp_api.py` 执行，详见 [bp-data-viewer SKILL.md](../bp-data-viewer/SKILL.md)。

### monthly_report_api.py（本 Skill 新增）

工作协同侧的汇报操作脚本，从工作区根目录执行：

```bash
python3 .cursor/skills/bp-monthly-report/scripts/monthly_report_api.py <action> [options]
```

| action | 说明 | 必填参数 | 可选参数 |
|--------|------|----------|----------|
| `collect_monthly_data` | 一次性采集 BP 结构 + 当月汇报数据，输出聚合 JSON | `--group_id`、`--month` | `--output` |
| `get_report_content` | 获取单条汇报正文内容 | `--report_id` | 无 |
| `send_report` | 发送月度汇报（工作协同） | `--receiver_emp_id`、`--title`、`--content_file` | `--sender_id` |
| `save_monthly_report` | 保存月报到 BP 系统（2.22 saveMonthlyReport） | `--group_id`、`--month`、`--content_file` | 无 |

## 批量生成

遍历全公司员工生成月报：

1. `get_all_periods` → 获取启用周期
2. `get_group_tree --only_personal` → 获取所有个人分组
3. 遍历每个个人分组，对每人执行 `collect_monthly_data` → 分步生成月报 → 发送 → 保存到 BP 系统

**注意**：批量生成前必须征得用户明确同意，并告知预计耗时。

## 重要约束

- 所有 ID 参数保持字符串原样传递，**严禁 parseInt 或 Number 转换**
- 月报内容**必须先展示给用户确认**，确认后才能发送
- **发送后必须保存**：调用 `send_report` 发送工作协同后，必须接着调用 `save_monthly_report` 将月报持久化到 BP 系统
- **禁止一步生成整篇报告**，必须走 3a → 3b → 3c → 3d 四步
- 第 2 章小节数量必须与实际 BP 目标数量一致，**不可写死**
- 第 2 章灯色判断到**目标级**，综合该目标下所有 KR 卡片得出
- 第 4 章灯色判断到**关键举措级**，每条举措单独带灯
- 所有灯色判断点统一使用**三灯判断块**（含人工确认入口）
- 最终报告中证据引用使用 `R{编号}` + 汇报标题，不内联正文
- 灯色文字使用 HTML `<span>` 彩色加粗渲染
- 灯色判断必须严格按 [references/traffic-light-rules.md](references/traffic-light-rules.md) 标准（注意灯规则版本）
- 证据处理必须严格按 [references/evidence-rules.md](references/evidence-rules.md) 标准
- 汇报计数以 reportId 去重后为准，内容相似的批量发送按一个工作事项计算
- 月份归集以汇报的 `createTime` 为准，不依赖关联时间
- 发送人默认 `400002`，对应 `BpGroupCheckService` 中的 `BP_SYSTEM_USER_MAP` 默认值
- 汇报接收人是员工本人（`employeeId`），**不是** `groupId`
- **查询数据**（collect_monthly_data 等）使用用户提供的 key，通过环境变量 `BP_OPEN_API_APP_KEY` 配置
- **发送汇报**（send_report）使用固定的机器人 key `1xmsXv2yv11OVqkd3zb5yG441sO5AB04`，已内置于脚本，无需额外配置
- 附件读取和在线汇报链接为待接入能力，**不可伪造**

## 环境配置

复用 `bp-data-viewer` 的环境变量：

| 变量名 | 说明 | 默认值 |
|--------|------|--------|
| `BP_OPEN_API_APP_KEY` | 数据查询用 API 密钥（**必填**） | 无（用户提供） |
| `SEND_REPORT_APP_KEY` | 发送汇报专用机器人密钥 | `1xmsXv2yv11OVqkd3zb5yG441sO5AB04`（已内置，无需配置） |
| `BP_OPEN_API_BASE_URL` | API 地址 | `https://sg-al-cwork-web.mediportal.com.cn/open-api` |

## 错误处理

- BP 数据获取失败时，提示用户检查 `BP_OPEN_API_APP_KEY` 配置
- 汇报发送失败时，保留已生成的月报内容，提示用户可手动重试发送
- 某个目标下无汇报数据时，在月报中标注"本月无汇报"并按灯色规则判断，不中断整体流程
