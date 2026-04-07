#!/usr/bin/env python3
import argparse
import json
import os
from typing import Any, Dict, Optional

from bp_client import BPClient, GetCurrentPeriod


def _print(obj: Dict[str, Any]) -> None:
    print(json.dumps(obj, ensure_ascii=False, indent=2))


def _ensure_employee_id(employee_id: Optional[str]) -> Optional[str]:
    return employee_id or os.getenv("BP_EMPLOYEE_ID") or os.getenv("EMPLOYEE_ID")


def CmdViewMyBp(client: BPClient, employee_id: Optional[str]) -> Dict[str, Any]:
    emp_id = _ensure_employee_id(employee_id)
    if not emp_id:
        return {"success": False, "error": "缺少 employeeId，请通过参数 --employee-id 或环境变量 BP_EMPLOYEE_ID/EMPLOYEE_ID 提供"}

    period = GetCurrentPeriod(client)
    if not period:
        return {"success": False, "error": "未找到启用周期"}

    group_ids = client.GetPersonalGroupIds([emp_id])
    if group_ids.get("resultCode") != 1:
        return {"success": False, "error": group_ids.get("resultMsg") or "获取个人分组失败"}

    group_id = (group_ids.get("data") or {}).get(emp_id)
    if not group_id:
        return {"success": False, "error": "未找到该员工的个人分组"}

    md = client.GetGroupMarkdown(group_id)
    if md.get("resultCode") != 1:
        return {"success": False, "error": md.get("resultMsg") or "获取分组 Markdown 失败"}

    return {"success": True, "period": {"id": period.get("id"), "name": period.get("name")}, "groupId": group_id, "markdown": md.get("data")}


def CmdViewGroupBp(client: BPClient, group_id: str) -> Dict[str, Any]:
    md = client.GetGroupMarkdown(group_id)
    if md.get("resultCode") != 1:
        return {"success": False, "error": md.get("resultMsg") or "获取分组 Markdown 失败"}
    return {"success": True, "groupId": group_id, "markdown": md.get("data")}


def CmdSearchGroups(client: BPClient, period_id: str, name: str) -> Dict[str, Any]:
    res = client.SearchGroups(period_id, name)
    if res.get("resultCode") != 1:
        return {"success": False, "error": res.get("resultMsg") or "搜索分组失败"}
    return {"success": True, "groups": res.get("data") or []}


def CmdSearchTasks(client: BPClient, group_id: str, name: str) -> Dict[str, Any]:
    res = client.SearchTasks(group_id, name)
    if res.get("resultCode") != 1:
        return {"success": False, "error": res.get("resultMsg") or "搜索任务失败"}
    return {"success": True, "tasks": res.get("data") or []}


def CmdListReports(
    client: BPClient,
    task_id: str,
    page_index: int,
    page_size: int,
    business_time_start: Optional[str],
    business_time_end: Optional[str],
    relation_time_start: Optional[str],
    relation_time_end: Optional[str],
) -> Dict[str, Any]:
    res = client.ListTaskReportsWithTimeRange(
        task_id,
        page_index=page_index,
        page_size=page_size,
        business_time_start=business_time_start,
        business_time_end=business_time_end,
        relation_time_start=relation_time_start,
        relation_time_end=relation_time_end,
    )
    if res.get("resultCode") != 1:
        return {"success": False, "error": res.get("resultMsg") or "查询汇报失败"}
    return {"success": True, "data": res.get("data")}


def CmdGetMonthlyReport(client: BPClient, group_id: str, report_month: str) -> Dict[str, Any]:
    res = client.GetMonthlyReportByMonth(group_id, report_month)
    if res.get("resultCode") != 1:
        return {"success": False, "error": res.get("resultMsg") or "查询月度汇报失败"}
    return {"success": True, "data": res.get("data")}


def main() -> None:
    parser = argparse.ArgumentParser(description="bp-manager-read（只读）命令行入口")
    sub = parser.add_subparsers(dest="command", required=True)

    p_view_my = sub.add_parser("view-my", help="查看我的 BP（Markdown）")
    p_view_my.add_argument("--employee-id", help="员工ID（可选；也可通过环境变量提供）")

    p_view_group = sub.add_parser("view-group", help="查看指定分组 BP（Markdown）")
    p_view_group.add_argument("--group-id", required=True, help="分组ID")

    p_search_groups = sub.add_parser("search-groups", help="按名称搜索分组")
    p_search_groups.add_argument("--period-id", required=True, help="周期ID")
    p_search_groups.add_argument("--name", required=True, help="名称关键词")

    p_search_tasks = sub.add_parser("search-tasks", help="按名称搜索任务")
    p_search_tasks.add_argument("--group-id", required=True, help="分组ID")
    p_search_tasks.add_argument("--name", required=True, help="名称关键词")

    p_reports = sub.add_parser("reports", help="查看任务关联汇报列表")
    p_reports.add_argument("--task-id", required=True, help="任务ID")
    p_reports.add_argument("--page-index", type=int, default=1, help="页码")
    p_reports.add_argument("--page-size", type=int, default=10, help="每页条数")
    p_reports.add_argument("--business-time-start", help="业务时间开始（yyyy-MM-dd HH:mm:ss，可选）")
    p_reports.add_argument("--business-time-end", help="业务时间结束（yyyy-MM-dd HH:mm:ss，可选）")
    p_reports.add_argument("--relation-time-start", help="关联时间开始（yyyy-MM-dd HH:mm:ss，可选）")
    p_reports.add_argument("--relation-time-end", help="关联时间结束（yyyy-MM-dd HH:mm:ss，可选）")

    p_monthly = sub.add_parser("monthly-report", help="按分组和月份查询月度汇报")
    p_monthly.add_argument("--group-id", required=True, help="分组ID（个人分组）")
    p_monthly.add_argument("--report-month", required=True, help="汇报月份（YYYY-MM）")

    args = parser.parse_args()

    client = BPClient()
    if args.command == "view-my":
        _print(CmdViewMyBp(client, args.employee_id))
        return
    if args.command == "view-group":
        _print(CmdViewGroupBp(client, args.group_id))
        return
    if args.command == "search-groups":
        _print(CmdSearchGroups(client, args.period_id, args.name))
        return
    if args.command == "search-tasks":
        _print(CmdSearchTasks(client, args.group_id, args.name))
        return
    if args.command == "reports":
        _print(
            CmdListReports(
                client,
                args.task_id,
                args.page_index,
                args.page_size,
                args.business_time_start,
                args.business_time_end,
                args.relation_time_start,
                args.relation_time_end,
            )
        )
        return
    if args.command == "monthly-report":
        _print(CmdGetMonthlyReport(client, args.group_id, args.report_month))
        return

    _print({"success": False, "error": f"未知命令：{args.command}"})


if __name__ == "__main__":
    main()

