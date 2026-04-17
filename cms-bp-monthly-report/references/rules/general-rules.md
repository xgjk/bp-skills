# 通用规则与约束

> 本文件为强制约束，贯穿整个月报生成流程（Step 1 – Step 4）。

---

## 通用约束

- 所有 ID 参数保持字符串原样传递，**严禁 parseInt 或 Number 转换**
- **严禁测试发送**：`send_report` 会真实推送给员工，只有报告内容完整生成且合规性校验全部通过后才能调用
- **校验通过后直接发送**，不再等待用户确认
- **禁止一步生成整篇报告**，必须走 3a → 3b → 3c → 3d 四步
- 汇报接收人是员工本人（`employeeId`），**不是** `groupId`

---

## 发送与重试规则

- 发送报错重试：脚本对"汇报人ID有误"和 `resultCode=401` 自动等待 60 秒后重试一次
- 发送人和 appKey 根据接收人企业自动匹配（corpId → sender + appKey 映射已内置在脚本中），查询数据使用用户提供的 key（`BP_OPEN_API_APP_KEY`），发送汇报使用与 sender 对应的机器人 key

---

## 失败处理

若任何步骤失败，必须立即更新状态为"失败"并记录原因：

```bash
python3 .openclaw/skills/bp-monthly-report/scripts/monthly_report_api.py update_report_status \
  --group_id "{groupId}" \
  --month "{YYYY-MM}" \
  --status 2 \
  --fail_reason "具体失败原因描述"
```

---

## 错误处理

- BP 数据获取失败时，提示用户检查 `BP_OPEN_API_APP_KEY` 配置
- 报告发送失败时，保留报告文件，提示用户可手动重试
- 脚本自动处理"汇报人ID有误"或 401 限流的重试；若重试仍失败，保留报告内容并提示用户排查
- 某个目标下无汇报数据时，在报告中标注"本月暂未收到工作汇报"并按灯色规则判断，不中断整体流程
