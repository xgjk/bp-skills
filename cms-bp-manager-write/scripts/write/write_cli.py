#!/usr/bin/env python3
import argparse
import json
from typing import Any, Dict, List, Optional, Tuple

from bp_client import BPClient


def _print(obj: Dict[str, Any]) -> None:
    print(json.dumps(obj, ensure_ascii=False, indent=2))


def _ensure_confirm(confirm: Optional[str]) -> Optional[str]:
    if confirm is None:
        return None
    return confirm.strip().lower()


def _pick_fields(source: Dict[str, Any], keys: List[str]) -> Dict[str, Any]:
    picked: Dict[str, Any] = {}
    for k in keys:
        if k in source:
            picked[k] = source.get(k)
    return picked


def _diff(before: Dict[str, Any], after: Dict[str, Any], keys: List[str]) -> List[Dict[str, Any]]:
    diffs: List[Dict[str, Any]] = []
    for k in keys:
        b = before.get(k)
        a = after.get(k)
        if b != a:
            diffs.append({"field": k, "before": b, "after": a})
    return diffs


def _fetch_task_detail_for_verify(client: BPClient, task_type: str, task_id: str) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
    """
    用于写前/写后校验的最小读取能力。
    task_type 取值：goal|keyResult|action
    """
    task_type_norm = (task_type or "").strip().lower()
    if task_type_norm == "goal":
        res = client.GetGoalDetail(task_id)
    elif task_type_norm == "keyresult":
        res = client.GetKeyResultDetail(task_id)
    elif task_type_norm == "action":
        res = client.GetActionDetail(task_id)
    else:
        return None, "taskType 不合法，必须是 goal/keyResult/action"

    if res.get("resultCode") != 1:
        return None, res.get("resultMsg") or "读取任务详情失败"
    data = res.get("data")
    if not isinstance(data, dict):
        return None, "读取任务详情失败：data 不是对象"
    return data, None


def main() -> None:
    parser = argparse.ArgumentParser(description="bp-manager-write（写入更新）命令行入口")
    sub = parser.add_subparsers(dest="command", required=True)

    p_add_kr = sub.add_parser("add-kr", help="新增关键成果（写操作）")
    p_add_kr.add_argument("--goal-id", required=True, help="目标ID")
    p_add_kr.add_argument("--name", required=True, help="关键成果名称")
    p_add_kr.add_argument("--confirm", required=True, help="二次确认：必须传 yes 才会执行写入")

    p_add_action = sub.add_parser("add-action", help="新增关键举措（写操作）")
    p_add_action.add_argument("--key-result-id", required=True, help="关键成果ID")
    p_add_action.add_argument("--name", required=True, help="关键举措名称")
    p_add_action.add_argument("--confirm", required=True, help="二次确认：必须传 yes 才会执行写入")

    p_delay = sub.add_parser("delay-reminder", help="发送延期提醒（写操作）")
    p_delay.add_argument("--receiver-emp-id", required=True, help="接收人员工ID")
    p_delay.add_argument("--task-name", required=True, help="任务名称")
    p_delay.add_argument("--plan-end-date", required=True, help="计划结束日期（字符串）")
    p_delay.add_argument("--content", help="自定义提醒内容（可选）")
    p_delay.add_argument("--confirm", required=True, help="二次确认：必须传 yes 才会执行写入")

    p_add_goal = sub.add_parser("add-goal", help="创建承接目标（写操作）")
    p_add_goal.add_argument("--name", required=True, help="目标名称")
    p_add_goal.add_argument("--group-id", required=True, help="分组ID（个人/组织）")
    p_add_goal.add_argument("--period-id", required=True, help="周期ID")
    p_add_goal.add_argument("--plan-start-date", help="开始日期（yyyy-MM-dd，可选）")
    p_add_goal.add_argument("--plan-end-date", help="结束日期（yyyy-MM-dd，可选）")
    p_add_goal.add_argument("--weight", help="权重 0-100（可选）")
    p_add_goal.add_argument("--upward-task-id", action="append", help="向上对齐任务ID（可多次传入）")
    p_add_goal.add_argument("--confirm", required=True, help="二次确认：必须传 yes 才会执行写入")

    p_align = sub.add_parser("align-task", help="建立/解除任务对齐关系（写操作）")
    p_align.add_argument("--current-task-id", required=True, help="本级任务ID")
    p_align.add_argument("--upward-task-id", action="append", help="向上对齐任务ID（可多次传入；传空则解除）")
    p_align.add_argument("--confirm", required=True, help="二次确认：必须传 yes 才会执行写入")

    p_update = sub.add_parser("update-task", help="通用任务更新（写操作，含差异确认单）")
    p_update.add_argument("--task-id", required=True, help="任务ID")
    p_update.add_argument("--task-type", required=True, choices=["goal", "keyResult", "action"], help="任务类型（用于写前/写后校验读取详情）")
    p_update.add_argument("--name", help="名称（可选）")
    p_update.add_argument("--plan-start-date", help="开始日期（yyyy-MM-dd，可选）")
    p_update.add_argument("--plan-end-date", help="结束日期（yyyy-MM-dd，可选）")
    p_update.add_argument("--measure-standard", help="衡量标准（KR/举措可选）")
    p_update.add_argument("--weight", help="权重（目标可选）")
    p_update.add_argument("--allow-sensitive", action="store_true", help="允许修改敏感字段（人员/部门等）。默认禁止。")
    p_update.add_argument("--responsible-emp-id", action="append", help="责任人ID（敏感字段，可多次传入）")
    p_update.add_argument("--responsible-dept-id", action="append", help="责任部门ID（敏感字段，可多次传入）")
    p_update.add_argument("--collaborator-id", action="append", help="协办人ID（敏感字段，可多次传入）")
    p_update.add_argument("--copy-to-id", action="append", help="抄送人ID（敏感字段，可多次传入）")
    p_update.add_argument("--supervisor-id", action="append", help="监督人ID（敏感字段，可多次传入）")
    p_update.add_argument("--observer-id", action="append", help="观察人ID（敏感字段，可多次传入）")
    p_update.add_argument("--confirm", required=True, help="二次确认：必须传 yes 才会执行写入")

    p_history = sub.add_parser("list-history", help="查询任务版本历史列表（读操作）")
    p_history.add_argument("--task-id", required=True, help="任务ID")
    p_history.add_argument("--page-index", type=int, default=1, help="页码（默认 1）")
    p_history.add_argument("--page-size", type=int, default=10, help="每页条数（默认 10）")

    p_history_detail = sub.add_parser("history-detail", help="查询快照详情（读操作）")
    p_history_detail.add_argument("--snapshot-id", required=True, help="快照ID")

    p_rollback = sub.add_parser("rollback", help="回退到指定版本（写操作）")
    p_rollback.add_argument("--snapshot-id", required=True, help="快照ID")
    p_rollback.add_argument("--confirm", required=True, help="二次确认：必须传 yes 才会执行写入")

    args = parser.parse_args()
    client = BPClient()

    if args.command in {"add-kr", "add-action", "delay-reminder", "add-goal", "align-task", "update-task", "rollback"}:
        confirm = _ensure_confirm(getattr(args, "confirm", None))
        if confirm != "yes":
            _print({"success": False, "error": "写操作已拦截：需要二次确认，请传 --confirm yes"})
            raise SystemExit(2)

    if args.command == "add-kr":
        res = client.AddKeyResult(args.goal_id, args.name)
        if res.get("resultCode") == 1:
            _print({"success": True, "keyResultId": res.get("data"), "message": f"已新增关键成果「{args.name}」"})
            return
        _print({"success": False, "error": res.get("resultMsg") or "新增关键成果失败"})
        return

    if args.command == "add-action":
        res = client.AddAction(args.key_result_id, args.name)
        if res.get("resultCode") == 1:
            _print({"success": True, "actionId": res.get("data"), "message": f"已新增关键举措「{args.name}」"})
            return
        _print({"success": False, "error": res.get("resultMsg") or "新增关键举措失败"})
        return

    if args.command == "delay-reminder":
        report_name = f"BP延期提醒 - {args.task_name}"
        content = args.content or f"您负责的任务「{args.task_name}」已延期，计划结束日期为{args.plan_end_date}，请尽快跟进处理。"
        res = client.SendDelayReport(args.receiver_emp_id, report_name, content)
        if res.get("resultCode") == 1:
            _print({"success": True, "reportId": res.get("data"), "message": f"已发送延期提醒给员工 {args.receiver_emp_id}"})
            return
        _print({"success": False, "error": res.get("resultMsg") or "发送延期提醒失败"})
        return

    if args.command == "add-goal":
        payload: Dict[str, Any] = {
            "name": args.name,
            "groupId": args.group_id,
            "periodId": args.period_id,
        }
        if args.plan_start_date:
            payload["planStartDate"] = args.plan_start_date
        if args.plan_end_date:
            payload["planEndDate"] = args.plan_end_date
        if args.weight is not None:
            payload["weight"] = args.weight
        if args.upward_task_id:
            payload["upwardTaskIdList"] = args.upward_task_id

        res = client.AddGoal(payload)
        if res.get("resultCode") == 1:
            _print({"success": True, "goalId": res.get("data"), "message": f"已创建目标「{args.name}」"})
            return
        _print({"success": False, "error": res.get("resultMsg") or "创建目标失败"})
        return

    if args.command == "align-task":
        upward = args.upward_task_id if args.upward_task_id is not None else None
        res = client.AlignTask(args.current_task_id, upward)
        if res.get("resultCode") == 1:
            _print({"success": True, "data": res.get("data"), "message": "对齐关系已更新"})
            return
        _print({"success": False, "error": res.get("resultMsg") or "对齐关系更新失败"})
        return

    if args.command == "update-task":
        before, err = _fetch_task_detail_for_verify(client, args.task_type, args.task_id)
        if err:
            _print({"success": False, "error": err})
            raise SystemExit(2)

        payload: Dict[str, Any] = {"taskId": args.task_id}
        allowed_fields: List[str] = []

        if args.name is not None:
            payload["name"] = args.name
            allowed_fields.append("name")
        if args.plan_start_date is not None:
            payload["planStartDate"] = args.plan_start_date
            allowed_fields.append("planStartDate")
        if args.plan_end_date is not None:
            payload["planEndDate"] = args.plan_end_date
            allowed_fields.append("planEndDate")
        if args.measure_standard is not None:
            payload["measureStandard"] = args.measure_standard
            allowed_fields.append("measureStandard")
        if args.weight is not None:
            payload["weight"] = args.weight
            allowed_fields.append("weight")

        sensitive_map: Dict[str, Any] = {
            "responsibleEmpIds": args.responsible_emp_id,
            "responsibleDeptIds": args.responsible_dept_id,
            "collaboratorIds": args.collaborator_id,
            "copyToIds": args.copy_to_id,
            "supervisorIds": args.supervisor_id,
            "observerIds": args.observer_id,
        }
        requested_sensitive = {k: v for k, v in sensitive_map.items() if v is not None}
        if requested_sensitive and not args.allow_sensitive:
            _print(
                {
                    "success": False,
                    "error": "检测到敏感字段修改请求（人员/部门等），默认禁止。若确需修改，请加 --allow-sensitive 并重新执行。",
                    "requestedSensitiveFields": requested_sensitive,
                }
            )
            raise SystemExit(2)
        if requested_sensitive and args.allow_sensitive:
            payload.update(requested_sensitive)
            allowed_fields.extend(list(requested_sensitive.keys()))

        if len(payload.keys()) <= 1:
            _print({"success": False, "error": "未指定任何可更新字段"})
            raise SystemExit(2)

        before_view = _pick_fields(before, allowed_fields)
        after_view = dict(before_view)
        for k in allowed_fields:
            if k in payload:
                after_view[k] = payload.get(k)
        diffs = _diff(before_view, after_view, allowed_fields)

        res = client.UpdateTask(payload)
        if res.get("resultCode") != 1:
            _print({"success": False, "error": res.get("resultMsg") or "更新任务失败", "diff": diffs})
            return

        after, err2 = _fetch_task_detail_for_verify(client, args.task_type, args.task_id)
        if err2:
            _print({"success": True, "message": "更新成功，但写后复核读取失败", "diff": diffs, "verifyError": err2})
            return
        after_real_view = _pick_fields(after, allowed_fields)
        verify_diffs = _diff(before_view, after_real_view, allowed_fields)
        _print(
            {
                "success": True,
                "message": "更新成功",
                "diffPlanned": diffs,
                "diffVerified": verify_diffs,
            }
        )
        return

    if args.command == "list-history":
        res = client.GetHistoryPage(args.task_id, page_index=args.page_index, page_size=args.page_size)
        if res.get("resultCode") == 1:
            _print({"success": True, "data": res.get("data")})
            return
        _print({"success": False, "error": res.get("resultMsg") or "查询版本历史失败"})
        return

    if args.command == "history-detail":
        res = client.GetHistoryDetail(args.snapshot_id)
        if res.get("resultCode") == 1:
            _print({"success": True, "data": res.get("data")})
            return
        _print({"success": False, "error": res.get("resultMsg") or "查询快照详情失败"})
        return

    if args.command == "rollback":
        res = client.Rollback(args.snapshot_id)
        if res.get("resultCode") == 1:
            _print({"success": True, "data": res.get("data"), "message": "已回退到指定版本"})
            return
        _print({"success": False, "error": res.get("resultMsg") or "版本回退失败"})
        return

    _print({"success": False, "error": f"未知命令：{args.command}"})


if __name__ == "__main__":
    main()

