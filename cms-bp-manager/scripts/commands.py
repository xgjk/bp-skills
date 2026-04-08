#!/usr/bin/env python3
"""
BP Manager 命令实现（只读 + 审计）

基于原版 bp-manager/scripts/commands.py 重建，移除写入命令（归属 cms-bp-manager-write）。
增强：时间范围过滤、月度汇报查询、UTF-8 终端兼容。
"""

import json
import argparse
import os
import sys
from typing import Dict, List, Optional, Any
from bp_client import BPClient, GetCurrentPeriod, FindMyGroup


def _configure_io_encoding() -> None:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    try:
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass


def _print(obj: Dict[str, Any]) -> None:
    print(json.dumps(obj, ensure_ascii=False, indent=2))


def _ensure_employee_id(employee_id: Optional[str]) -> Optional[str]:
    return employee_id or os.getenv("BP_EMPLOYEE_ID") or os.getenv("EMPLOYEE_ID")


# ==================== 查看 BP 命令 ====================

def CmdViewMyBp(client: BPClient, employee_id: Optional[str] = None) -> Dict[str, Any]:
    """查看我的 BP"""
    emp_id = _ensure_employee_id(employee_id)
    if not emp_id:
        return {"success": False, "error": "缺少 employeeId，请通过参数 --employee-id 或环境变量 BP_EMPLOYEE_ID/EMPLOYEE_ID 提供"}

    period = GetCurrentPeriod(client)
    if not period:
        return {"success": False, "error": "未找到启用的周期"}

    period_id = period["id"]
    group_id = FindMyGroup(client, period_id, emp_id)
    if not group_id:
        return {"success": False, "error": "未找到该员工的个人分组"}

    result = client.GetGroupMarkdown(group_id)
    if result.get("resultCode") != 1:
        return {"success": False, "error": result.get("resultMsg") or "获取 BP 失败"}

    return {
        "success": True,
        "period": {"id": period.get("id"), "name": period.get("name")},
        "groupId": group_id,
        "markdown": result["data"],
    }


def CmdViewGroupBp(client: BPClient, group_id: str) -> Dict[str, Any]:
    """查看指定分组的 BP"""
    result = client.GetGroupMarkdown(group_id)
    if result.get("resultCode") != 1:
        return {"success": False, "error": result.get("resultMsg") or "获取 BP 失败"}
    return {"success": True, "groupId": group_id, "markdown": result["data"]}


def CmdViewSubordinateBp(client: BPClient, subordinate_name: str, period_id: Optional[str] = None) -> Dict[str, Any]:
    """查看下属的 BP"""
    if not period_id:
        period = GetCurrentPeriod(client)
        if not period:
            return {"success": False, "error": "未找到启用的周期"}
        period_id = period["id"]

    result = client.SearchGroups(period_id, subordinate_name)
    if result.get("resultCode") != 1 or not result.get("data"):
        return {"success": False, "error": f"未找到名为 '{subordinate_name}' 的分组"}

    groups = result["data"]
    target_group = None
    for g in groups:
        if g.get("type") == "personal":
            target_group = g
            break
    if not target_group:
        target_group = groups[0]

    return CmdViewGroupBp(client, target_group["id"])


# ==================== 查看汇报历史命令 ====================

def CmdViewReports(
    client: BPClient,
    task_id: str,
    page_index: int = 1,
    page_size: int = 10,
    business_time_start: Optional[str] = None,
    business_time_end: Optional[str] = None,
    relation_time_start: Optional[str] = None,
    relation_time_end: Optional[str] = None,
) -> Dict[str, Any]:
    """查看任务的汇报历史（支持时间范围过滤）"""
    result = client.ListTaskReportsWithTimeRange(
        task_id,
        page_index=page_index,
        page_size=page_size,
        business_time_start=business_time_start,
        business_time_end=business_time_end,
        relation_time_start=relation_time_start,
        relation_time_end=relation_time_end,
    )
    if result.get("resultCode") != 1:
        return {"success": False, "error": result.get("resultMsg") or "获取汇报历史失败"}
    data = result["data"]
    return {"success": True, "total": data.get("total", 0), "reports": data.get("list", [])}


# ==================== 月度汇报命令 ====================

def CmdGetMonthlyReport(client: BPClient, group_id: str, report_month: str) -> Dict[str, Any]:
    """按分组和月份查询月度汇报"""
    result = client.GetMonthlyReportByMonth(group_id, report_month)
    if result.get("resultCode") != 1:
        return {"success": False, "error": result.get("resultMsg") or "查询月度汇报失败"}
    return {"success": True, "data": result.get("data")}


# ==================== 搜索命令 ====================

def CmdSearchTasks(client: BPClient, group_id: str, keyword: str) -> Dict[str, Any]:
    """搜索任务"""
    result = client.SearchTasks(group_id, keyword)
    if result.get("resultCode") != 1:
        return {"success": False, "error": result.get("resultMsg") or "搜索任务失败"}
    return {"success": True, "tasks": result.get("data") or []}


def CmdSearchGroups(client: BPClient, period_id: str, keyword: str) -> Dict[str, Any]:
    """搜索分组"""
    result = client.SearchGroups(period_id, keyword)
    if result.get("resultCode") != 1:
        return {"success": False, "error": result.get("resultMsg") or "搜索分组失败"}
    return {"success": True, "groups": result.get("data") or []}


# ==================== AI 检查命令 ====================

def CmdCheckBp(client: BPClient, group_id: str) -> Dict[str, Any]:
    """
    AI 检查 BP 质量（基于康哲规则）

    检查项包括：
    1. 结构完整性：是否按 G-R-A 三层拆解
    2. 衡量标准：所有关键成果是否有合格的衡量标准
    3. 承接关系：是否正确承接上级任务
    4. 举措可执行性：关键举措是否具体可执行
    5. 时间合理性：时间范围是否合理
    """
    result = client.GetGroupMarkdown(group_id)
    if result.get("resultCode") != 1:
        return {"success": False, "error": "获取 BP 失败"}

    return {
        "success": True,
        "markdown": result["data"],
        "message": "BP 数据已获取，请结合 references/kangzhe-rules.md 中的康哲规则进行 AI 深度分析",
    }


# ==================== 周期列表命令 ====================

def CmdListPeriods(client: BPClient, name: Optional[str] = None) -> Dict[str, Any]:
    """列出周期列表"""
    result = client.ListPeriods(name)
    if result.get("resultCode") != 1:
        return {"success": False, "error": result.get("resultMsg") or "查询周期列表失败"}
    return {"success": True, "periods": result.get("data") or []}


# ==================== 主函数 ====================

def main() -> None:
    _configure_io_encoding()
    parser = argparse.ArgumentParser(description="BP Manager 命令行工具（只读 + 审计）")
    sub = parser.add_subparsers(dest="command", required=True, help="可用命令")

    p_view_my = sub.add_parser("view-my", help="查看我的 BP")
    p_view_my.add_argument("--employee-id", help="员工ID（可选；也可通过环境变量提供）")

    p_view_group = sub.add_parser("view-group", help="查看指定分组的 BP")
    p_view_group.add_argument("--group-id", required=True, help="分组ID")

    p_view_subordinate = sub.add_parser("view-subordinate", help="查看下属的 BP")
    p_view_subordinate.add_argument("--name", required=True, help="下属姓名")
    p_view_subordinate.add_argument("--period-id", help="周期ID（可选）")

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

    p_search_tasks = sub.add_parser("search-tasks", help="搜索任务")
    p_search_tasks.add_argument("--group-id", required=True, help="分组ID")
    p_search_tasks.add_argument("--keyword", required=True, help="搜索关键词")

    p_search_groups = sub.add_parser("search-groups", help="搜索分组")
    p_search_groups.add_argument("--period-id", required=True, help="周期ID")
    p_search_groups.add_argument("--keyword", required=True, help="搜索关键词")

    p_check = sub.add_parser("check-bp", help="AI 检查 BP 质量（基于康哲规则）")
    p_check.add_argument("--group-id", required=True, help="分组ID")

    p_periods = sub.add_parser("list-periods", help="列出周期列表（可选按名称模糊搜索）")
    p_periods.add_argument("--name", help="周期名称关键词（可选）")

    args = parser.parse_args()
    client = BPClient()

    if args.command == "view-my":
        _print(CmdViewMyBp(client, args.employee_id))
    elif args.command == "view-group":
        _print(CmdViewGroupBp(client, args.group_id))
    elif args.command == "view-subordinate":
        _print(CmdViewSubordinateBp(client, args.name, args.period_id))
    elif args.command == "reports":
        _print(CmdViewReports(
            client, args.task_id, args.page_index, args.page_size,
            args.business_time_start, args.business_time_end,
            args.relation_time_start, args.relation_time_end,
        ))
    elif args.command == "monthly-report":
        _print(CmdGetMonthlyReport(client, args.group_id, args.report_month))
    elif args.command == "search-tasks":
        _print(CmdSearchTasks(client, args.group_id, args.keyword))
    elif args.command == "search-groups":
        _print(CmdSearchGroups(client, args.period_id, args.keyword))
    elif args.command == "check-bp":
        _print(CmdCheckBp(client, args.group_id))
    elif args.command == "list-periods":
        _print(CmdListPeriods(client, args.name))
    else:
        _print({"success": False, "error": f"未知命令：{args.command}"})


if __name__ == "__main__":
    main()
