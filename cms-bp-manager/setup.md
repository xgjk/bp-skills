# BP Manager 安装说明

## 前置条件

1. **Python 3.8+**
2. **BP API 访问权限**（需要 BP_APP_KEY）
3. **网络访问**（能访问 `https://sg-al-cwork-web.mediportal.com.cn/open-api`）

---

## 安装步骤

### 1. 设置环境变量

```bash
# 在 ~/.zshrc 或 ~/.bashrc 中添加
export BP_APP_KEY="your-app-key-here"
```

### 2. 验证安装

```bash
# 测试 API 连接
python3 scripts/bp_client.py
```

---

## 配置说明

### 环境变量

| 变量名 | 必需 | 说明 |
|--------|------|------|
| BP_APP_KEY | ✅ | BP API 的 appKey，从玄关开放平台获取 |

### 配置文件（可选）

可以创建 `.env` 文件存储环境变量：
```bash
BP_APP_KEY=your-app-key-here
```

---

## 使用方式

### 在对话中使用

在对话中直接说：
- "查看我的 BP"
- "查看张三的 BP"
- "检查我的 BP"
- "查看目标 A4-1 的汇报历史"
- "搜索关于客户拜访的任务"

### 命令行使用

```bash
# 查看我的 BP
python3 scripts/commands.py view-my

# 查看指定分组的 BP
python3 scripts/commands.py view-group --group-id <group-id>

# 查看下属的 BP
python3 scripts/commands.py view-subordinate --name "张三"

# AI 检查 BP 质量
python3 scripts/commands.py check-bp --group-id <group-id>

# 查看汇报历史（支持时间过滤）
python3 scripts/commands.py reports --task-id <task-id>

# 按分组和月份查询月度汇报
python3 scripts/commands.py monthly-report --group-id <group-id> --report-month 2026-03

# 搜索任务
python3 scripts/commands.py search-tasks --group-id <group-id> --keyword "关键词"

# 搜索分组
python3 scripts/commands.py search-groups --period-id <period-id> --keyword "关键词"

# 列出周期列表
python3 scripts/commands.py list-periods
```

> **写入操作（新增KR/新增举措/延期提醒）请使用 `cms-bp-manager-write`**

---

## 故障排查

### 问题 1：提示缺少 BP_APP_KEY
**解决方案**：确保已设置环境变量
```bash
echo $BP_APP_KEY  # 检查是否输出 appKey
```

### 问题 2：API 调用失败（resultCode: 610002）
**解决方案**：BP_APP_KEY 无效，请从玄关开放平台获取正确的 appKey

### 问题 3：找不到分组
**解决方案**：
1. 确认姓名拼写正确
2. 确认有权限访问该分组
3. 确认周期正确（可能不是当前周期）

### 问题 4：无访问权限（resultCode: 610015）
**解决方案**：联系管理员开通相应权限

---

## 更新日志

| 版本 | 日期 | 变更 |
|------|------|------|
| v1.0.0 | 2026-04-04 | 初版发布（原 bp-manager） |
| v2.0.0 | 2026-04-08 | 基于原版重建：写入能力拆分至 cms-bp-manager-write；新增月度汇报查询、时间范围过滤、UTF-8 兼容 |
