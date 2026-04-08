---
name: cms-bp-manager
description: BP管理助手 — 查看/管理自己与下级的BP（目标/关键成果/关键举措）、AI质量检查。触发词：bp/BP/BP管理/BP目标/BP成果/BP举措/衡量标准/对齐/关键任务/关键成果/上级BP/下级BP/承接/目标管理/OKR/KR/我的目标/我的成果/查看BP/查看目标/检查BP/审计BP。
metadata:
  homepage: https://github.com/xgjk/bp-skills/tree/main/cms-bp-manager
  version: v2.0.1
  status: ACTIVE
tools_provided:
  - name: bp_client
    category: exec
    risk_level: low
    permission: exec
    description: BP系统API客户端，封装所有BP只读与审计相关接口调用
    status: active
  - name: commands
    category: exec
    risk_level: low
    permission: exec
    description: BP管理命令集合（查看/搜索/检查BP）
    status: active
dependencies:
  - cms-auth-skills
---

# BP Manager（读 + 审计）

> BP 管理助手 — 查看/管理自己与下级的BP，AI质量检查（基于康哲规则）

---

## 角色定位

BP Manager 是面向管理者和员工的 BP 日常管理工具，本技能承载**只读查询 + AI 审计检查**能力：

1. **BP 查看**：查看自己或下级的 BP（目标/关键成果/关键举措）
2. **AI 检查**：基于康哲规则检查 BP 质量（结构/承接/衡量标准）
3. **汇报查看**：查看任务关联的汇报历史
4. **搜索功能**：按名称搜索任务或分组
5. **月度汇报查询**：按分组+月份查询月度汇报
6. **下级BP建议**：为下级的 BP 提供改进建议

> **写入能力（新增KR/新增举措/延期提醒）已拆分至** `cms-bp-manager-write`

---

## 核心场景

### 场景一：查看 BP

**用户意图**：快速了解 BP 全貌

**触发词**：
- "查看我的 BP"
- "查看下属的 BP"
- "查看产品中心的 BP"

**执行流程**：
1. 识别用户身份（通过员工ID）
2. 获取周期列表，选择当前周期
3. 获取分组树，定位到目标分组
4. 调用 `getGroupMarkdown` 获取完整 BP
5. 格式化输出给用户

**示例**：
```
用户：查看我的 BP
助手：正在获取您的 BP...
[输出 Markdown 格式的 BP 内容]
```

---

### 场景二：AI 检查 BP

**用户意图**：检查 BP 是否符合康哲规则

**触发词**：
- "检查我的 BP"
- "BP 质量检查"
- "帮我检查一下这个 BP"
- "审计 BP"

**执行流程**：
1. 获取目标 BP 内容（Markdown 格式）
2. 基于康哲规则进行检查：
   - 结构完整性：是否按 G-R-A 三层拆解
   - 承接关系：下级目标是否承接上级关键举措
   - 衡量标准：是否符合 SMART 原则
   - 层级深度：是否符合所在层级要求
3. 输出检查结果和改进建议

**检查规则**（来自 `references/kangzhe-rules.md`）：
- **集团层级**：拆解到 2 层（目标 → 关键成果）
- **中心/部门/员工层级**：拆解到 3 层（目标 → 关键成果 → 关键举措）
- **衡量标准**：必须包含指标/阈值/口径/数据源/统计频率
- **承接规则**：下级目标承接上级关键成果/关键举措

**示例**：
```
用户：检查我的 BP
助手：正在检查您的 BP...

检查结果：
✅ 结构完整性：通过（3层结构完整）
✅ 承接关系：通过（目标承接了上级关键举措）
⚠️ 衡量标准：关键成果 1.2 缺少数据源
✅ 层级深度：通过（符合部门层级要求）

建议：
- 为关键成果 1.2 补充数据源信息
```

---

### 场景三：下级 BP 建议

**用户意图**：为下级的 BP 提供创建关键举措的建议

**触发词**：
- "帮我看看下属的 BP"
- "给下级提点建议"
- "为下属的 BP 提建议"

**执行流程**：
1. 获取下级 BP 内容
2. 分析 BP 内容，识别：
   - 哪些关键成果缺少关键举措
   - 哪些关键举措过于空泛，需要拆解
   - 哪些关键举措缺少承接人
3. 基于分析结果，生成改进建议
4. 输出建议列表

**示例**：
```
用户：帮我看看张三的 BP，给他提点建议
助手：正在分析张三的 BP...

建议为张三的 BP 改进以下内容：

**关键成果 1.1：客户拜访量达到50家**
- 建议新增举措：建立拜访记录系统，记录每次拜访的详细信息
- 建议新增举措：制定月度拜访计划，明确每周拜访目标

**关键成果 1.2：签约客户数达到20家**
- 建议新增举措：重点客户专项跟进，建立客户档案
- 建议新增举措：每周五回报跟进进度，及时调整策略

如需创建这些关键举措，请使用写入技能 cms-bp-manager-write
```

---

### 场景四：查看汇报历史

**用户意图**：查看某个任务关联的汇报历史

**触发词**：
- "查看目标 X 的汇报历史"
- "这个任务的汇报记录"

**执行流程**：
1. 识别目标任务
2. 调用 `pageAllReports` 接口（支持时间范围过滤）
3. 格式化输出汇报列表

**示例**：
```
用户：查看目标 A4-1 的汇报历史
助手：正在获取汇报历史...

目标【A4-1】的汇报历史（共5条）：

1. 手动汇报 - 2026-03-10
   - 标题： Q1 进度汇报
   - 业务时间： 2026-03-08

2. AI汇报 - 2026-03-05
   - 标题： AI进度分析
   - 业务时间： 2026-03-01

...
```

---

### 场景五：搜索任务

**用户意图**：按名称搜索 BP 任务

**触发词**：
- "搜索关于客户拜访的任务"
- "找一下包含'全栈'的任务"

**执行流程**：
1. 识别搜索关键词
2. 确定搜索范围（分组ID）
3. 调用 `searchTaskByName` 接口
4. 输出搜索结果

**示例**：
```
用户：搜索关于客户拜访的任务
助手：正在搜索...

找到 2 个相关任务：

1. 【关键成果】客户拜访量达到50家
   - 分组： 技术部
   - 状态： 进行中
   - 承接人： 张三

2. 【关键举措】每周拜访5家客户
   - 分组： 技术部
   - 状态： 进行中
   - 承接人： 李四
```

---

### 场景六：查询月度汇报

**用户意图**：按分组+月份查询月度汇报

**触发词**：
- "查看3月份的月度汇报"
- "月度汇报查询"

**执行流程**：
1. 确认分组ID和汇报月份（YYYY-MM）
2. 调用 `getMonthlyReportByMonth` 接口
3. 格式化输出月度汇报内容

---

## 写入能力（已拆分）

以下场景已拆分至 `cms-bp-manager-write`，本技能不再承载：

- **新增关键成果**：为某个目标添加新的关键成果 → `cms-bp-manager-write`
- **新增关键举措**：为某个关键成果添加关键举措 → `cms-bp-manager-write`
- **延期提醒**：向指定员工发送延期提醒 → `cms-bp-manager-write`

---

## 环境变量

| 变量名 | 说明 | 获取方式 |
|--------|------|----------|
| BP_APP_KEY | BP 系统 API 密钥 | 从玄关开放平台获取 |

---

## API 接口清单

### 本技能使用的接口（只读）

| 接口 | 方法 | 用途 |
|-----|------|------|
| `GET /bp/period/list` | 获取周期列表 | 选择工作周期 |
| `GET /bp/group/list` | 获取分组树 | 导航到目标分组 |
| `POST /bp/group/getPersonalGroupIds` | 批量获取个人分组ID | 快速定位员工 |
| `GET /bp/task/v2/getSimpleTree` | 获取BP任务树 | 了解完整结构 |
| `GET /bp/goal/list` | 获取目标列表 | 查看目标概览 |
| `GET /bp/goal/{goalId}/detail` | 获取目标详情 | 查看单个目标完整信息 |
| `GET /bp/keyResult/list` | 获取关键成果列表 | |
| `GET /bp/keyResult/{keyResultId}/detail` | 获取关键成果详情 | |
| `GET /bp/action/list` | 获取关键举措列表 | |
| `GET /bp/action/{actionId}/detail` | 获取关键举措详情 | |
| `GET /bp/group/markdown` | 获取分组BP Markdown | AI 分析友好 |
| `POST /bp/group/batchGetKeyPositionMarkdown` | 批量获取关键岗位详情 | |
| `GET /bp/task/children` | 获取任务子树骨架 | |
| `POST /bp/task/relation/pageAllReports` | 查询任务关联汇报 | 支持时间范围过滤 |
| `GET /bp/delayReport/list` | 查询延期汇报历史 | |
| `GET /bp/task/v2/searchByName` | 按名称搜索任务 | |
| `GET /bp/group/searchByName` | 按名称搜索分组 | |
| `GET /bp/monthly/report/getByMonth` | 按分组+月份查询月度汇报 | |

### 写入接口（归属 cms-bp-manager-write）

| 接口 | 方法 | 用途 |
|-----|------|------|
| `POST /bp/task/v2/addKeyResult` | 新增关键成果 | → cms-bp-manager-write |
| `POST /bp/task/v2/addAction` | 新增关键举措 | → cms-bp-manager-write |
| `POST /bp/delayReport/send` | 发送延期提醒汇报 | → cms-bp-manager-write |

---

## 数据模型

### Period（周期）
```typescript
interface Period {
  id: string;        // 周期 ID
  name: string;      // 周期名称
  status: number;    // 1=启用，0=未启用
}
```

### Group（分组）
```typescript
interface Group {
  id: string;           // 分组 ID
  name: string;         // 分组名称
  type: 'org' | 'personal';  // 组织/个人
  levelNumber: string;  // 层级编码
  employeeId?: string;  // 个人分组时的员工ID
  parentId?: string;    // 父分组 ID
  childCount?: number;  // 下级分组数量
  children?: Group[];   // 子分组
}
```

### Goal（目标）
```typescript
interface Goal {
  id: string;              // 目标 ID
  name: string;            // 目标名称
  fullLevelNumber: string; // 目标编码
  statusDesc: string;      // 状态描述
  reportCycle: string;     // 汇报周期
  planDateRange: string;   // 计划时间范围
  taskUsers: TaskUser[];   // 参与人
  krCount?: number;        // 关键成果数量
  actionCount?: number;    // 关键举措数量
  keyResults?: KeyResult[];// 关键成果列表
}
```

### KeyResult（关键成果）
```typescript
interface KeyResult {
  id: string;              // 关键成果 ID
  name: string;            // 关键成果名称
  fullLevelNumber: string; // 编码
  statusDesc: string;      // 状态描述
  measureStandard: string; // 衡量标准
  reportCycle: string;     // 汇报周期
  planDateRange: string;   // 计划时间范围
  taskUsers: TaskUser[];   // 参与人
  actionCount?: number;    // 关键举措数量
  actions?: Action[];      // 关键举措列表
}
```

### Action（关键举措）
```typescript
interface Action {
  id: string;              // 关键举措 ID
  name: string;            // 关键举措名称
  fullLevelNumber: string; // 编码
  statusDesc: string;      // 状态描述
  reportCycle: string;     // 汇报周期
  planDateRange: string;   // 计划时间范围
  taskUsers: TaskUser[];   // 参与人
}
```

### TaskUser（任务参与人）
```typescript
interface TaskUser {
  taskId: string;   // 任务 ID
  role: string;     // 角色：承接人/协办人/抄送人/监督人/观察人
  empList: Employee[]; // 员工列表
}
```

### Employee（员工）
```typescript
interface Employee {
  id: string;   // 员工 ID
  name: string; // 员工姓名
}
```

---

## 错误处理

| 错误码 | 说明 | 处理建议 |
|--------|------|----------|
| 1 | 请求成功 | 正常处理 |
| 0 | 通用失败 | 提示用户稍后重试 |
| 610002 | appKey 无效 | 检查 BP_APP_KEY 环境变量 |
| 610015 | 无访问权限 | 提示用户无权限访问该资源 |

---

## 使用注意事项

1. **API 限制**：当前系统不支持编辑和删除操作，只能通过 Web UI 进行
2. **权限控制**：部分接口有数据权限校验，无权限时返回空列表
3. **周期管理**：建议每次操作前先确认当前周期
4. **性能考虑**：`getGroupMarkdown` 返回完整 BP，Token 消耗较大，适合 AI 分析场景
5. **鉴权依赖**：所有接口调用统一依赖 `cms-auth-skills`，脚本不实现登录与换 token

---

## 审计输出要求（强制）

- 结论必须精确引用到具体对象（编号+名称）
- 不允许使用"部分/某些/个别"等模糊指代
- 问题必须包含：**对象精确引用 + 严重等级 + 原因 + 建议**
- 审计维度覆盖：基础合规、向上对齐、向下承接、GAP 分析

---

## 能力树

```text
cms-bp-manager/
├── SKILL.md
├── README.md
├── setup.md
├── design/
│   └── design.md
├── references/
│   ├── api-endpoints.md
│   ├── api-request--20260404.md
│   ├── kangzhe-rules.md
│   ├── maintenance.md
│   └── audit/
│       └── README.md
└── scripts/
    ├── bp_client.py
    └── commands.py
```

---

## 版本历史

| 版本 | 日期 | 变更说明 |
|------|------|----------|
| v1.0.0 | 2026-04-04 | 初版，包含 BP 查看/管理/检查/提醒功能（原 bp-manager） |
| v2.0.0 | 2026-04-08 | 重构：基于原版 bp-manager 重建，写入能力拆分至 cms-bp-manager-write；新增月度汇报查询、时间范围过滤、UTF-8 兼容 |
