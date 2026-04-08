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
import subprocess
import urllib.error
import urllib.request
from pathlib import Path
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

def _is_truthy(value: Optional[str]) -> bool:
    if value is None:
        return False
    return value.strip().lower() in {"1", "true", "yes", "y", "on"}


def _parse_semver(version: str) -> Optional[List[int]]:
    s = (version or "").strip()
    if not s:
        return None
    if s.startswith("v") or s.startswith("V"):
        s = s[1:]
    parts = s.split(".")
    nums: List[int] = []
    for p in parts:
        p = p.strip()
        if not p.isdigit():
            return None
        nums.append(int(p))
    if not nums:
        return None
    while len(nums) < 3:
        nums.append(0)
    return nums[:3]


def _compare_semver(a: str, b: str) -> Optional[int]:
    """
    比较 a 与 b（语义版本号，支持 v 前缀）。
    返回：1 表示 a>b；0 表示相等；-1 表示 a<b；None 表示无法比较。
    """
    aa = _parse_semver(a)
    bb = _parse_semver(b)
    if aa is None or bb is None:
        return None
    if aa == bb:
        return 0
    return 1 if aa > bb else -1


def _read_local_skill_version() -> Optional[str]:
    """
    从本技能的 SKILL.md 头部读取 metadata.version（不引入第三方 YAML 依赖）。
    """
    try:
        skill_md = Path(__file__).resolve().parents[1] / "SKILL.md"
        text = skill_md.read_text(encoding="utf-8")
    except Exception:
        return None

    in_front_matter = False
    for line in text.splitlines():
        if line.strip() == "---" and not in_front_matter:
            in_front_matter = True
            continue
        if line.strip() == "---" and in_front_matter:
            break
        if not in_front_matter:
            continue
        # 只匹配顶层/二级缩进的 version 字段（metadata.version）
        # 例如：  version: v2.0.1
        if line.lstrip().startswith("version:"):
            _, v = line.split(":", 1)
            return v.strip().strip("\"'") or None
    return None


def _fetch_latest_release_tag(timeout_seconds: float = 3.0) -> Optional[str]:
    """
    从 GitHub Release 拉取最新 tag（无鉴权；失败则返回 None，不影响主业务）。
    """
    url = "https://api.github.com/repos/xgjk/bp-skills/releases/latest"
    req = urllib.request.Request(
        url,
        headers={
            "Accept": "application/vnd.github+json",
            "User-Agent": "cms-bp-manager-update-check",
        },
        method="GET",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout_seconds) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            tag = (data or {}).get("tag_name")
            if isinstance(tag, str) and tag.strip():
                return tag.strip()
            return None
    except Exception:
        return None


def _maybe_check_and_update(allow_auto_update: bool, allow_prompt: bool) -> Optional[Dict[str, Any]]:
    """
    - 默认只做检查，不阻断主命令执行
    - 检测到更新：返回 updateInfo；必要时自动更新或提示更新
    """
    local_version = _read_local_skill_version()
    latest_tag = _fetch_latest_release_tag()
    if not local_version or not latest_tag:
        return None

    cmp = _compare_semver(latest_tag, local_version)
    if cmp is None or cmp <= 0:
        return None

    install_cmd = "npx clawhub@latest install cms-bp-manager --force"
    info: Dict[str, Any] = {
        "hasUpdate": True,
        "currentVersion": local_version,
        "latestVersion": latest_tag,
        "installCommand": install_cmd,
    }

    if allow_auto_update:
        try:
            proc = subprocess.run(install_cmd, shell=True, check=False, capture_output=True, text=True)
            info["autoUpdateAttempted"] = True
            info["autoUpdateExitCode"] = proc.returncode
            if proc.returncode == 0:
                info["autoUpdateSuccess"] = True
            else:
                info["autoUpdateSuccess"] = False
                info["autoUpdateError"] = (proc.stderr or proc.stdout or "").strip()[:2000]
        except Exception as exc:
            info["autoUpdateAttempted"] = True
            info["autoUpdateSuccess"] = False
            info["autoUpdateError"] = str(exc)
        return info

    if allow_prompt and sys.stdin.isatty():
        try:
            sys.stderr.write(
                f\"检测到 cms-bp-manager 有新版本：{local_version} → {latest_tag}\\n是否现在更新？(yes/no)：\"
            )
            sys.stderr.flush()
            ans = (sys.stdin.readline() or \"\").strip().lower()
            if ans in {\"yes\", \"y\"}:
                proc = subprocess.run(install_cmd, shell=True, check=False, capture_output=True, text=True)
                info[\"prompted\"] = True
                info[\"userAccepted\"] = True
                info[\"updateExitCode\"] = proc.returncode
                if proc.returncode != 0:
                    info[\"updateError\"] = (proc.stderr or proc.stdout or \"\").strip()[:2000]
            else:
                info[\"prompted\"] = True
                info[\"userAccepted\"] = False
        except Exception as exc:
            info[\"prompted\"] = True
            info[\"promptError\"] = str(exc)
        return info

    info["prompted"] = False
    info["message"] = "检测到新版本，可手动执行 installCommand 更新。"
    return info


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
    parser.add_argument("--skip-update-check", action="store_true", help="跳过版本更新检查")
    parser.add_argument("--auto-update", action="store_true", help="发现新版本时自动执行更新安装命令")
    parser.add_argument("--prompt-update", action="store_true", help="发现新版本时提示是否更新（仅在 TTY 下生效）")
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
    # 默认策略：检查更新但不打断业务；仅输出提示信息。
    # 可通过参数或环境变量切换为自动更新/提示更新。
    update_info: Optional[Dict[str, Any]] = None
    if not args.skip_update_check and not _is_truthy(os.getenv("BP_MANAGER_SKIP_UPDATE_CHECK")):
        allow_auto = args.auto_update or _is_truthy(os.getenv("BP_MANAGER_AUTO_UPDATE"))
        allow_prompt = args.prompt_update or _is_truthy(os.getenv("BP_MANAGER_PROMPT_UPDATE"))
        update_info = _maybe_check_and_update(allow_auto_update=allow_auto, allow_prompt=allow_prompt)

    client = BPClient()

    if args.command == "view-my":
        res = CmdViewMyBp(client, args.employee_id)
        if update_info:
            res["updateInfo"] = update_info
        _print(res)
    elif args.command == "view-group":
        res = CmdViewGroupBp(client, args.group_id)
        if update_info:
            res["updateInfo"] = update_info
        _print(res)
    elif args.command == "view-subordinate":
        res = CmdViewSubordinateBp(client, args.name, args.period_id)
        if update_info:
            res["updateInfo"] = update_info
        _print(res)
    elif args.command == "reports":
        res = CmdViewReports(
            client, args.task_id, args.page_index, args.page_size,
            args.business_time_start, args.business_time_end,
            args.relation_time_start, args.relation_time_end,
        )
        if update_info:
            res["updateInfo"] = update_info
        _print(res)
    elif args.command == "monthly-report":
        res = CmdGetMonthlyReport(client, args.group_id, args.report_month)
        if update_info:
            res["updateInfo"] = update_info
        _print(res)
    elif args.command == "search-tasks":
        res = CmdSearchTasks(client, args.group_id, args.keyword)
        if update_info:
            res["updateInfo"] = update_info
        _print(res)
    elif args.command == "search-groups":
        res = CmdSearchGroups(client, args.period_id, args.keyword)
        if update_info:
            res["updateInfo"] = update_info
        _print(res)
    elif args.command == "check-bp":
        res = CmdCheckBp(client, args.group_id)
        if update_info:
            res["updateInfo"] = update_info
        _print(res)
    elif args.command == "list-periods":
        res = CmdListPeriods(client, args.name)
        if update_info:
            res["updateInfo"] = update_info
        _print(res)
    else:
        res = {"success": False, "error": f"未知命令：{args.command}"}
        if update_info:
            res["updateInfo"] = update_info
        _print(res)


if __name__ == "__main__":
    main()
