#!/usr/bin/env python3
import argparse
import json
from typing import Any, Dict, Optional

from bp_client import BPClient


def _print(obj: Dict[str, Any]) -> None:
    print(json.dumps(obj, ensure_ascii=False, indent=2))


def _ensure_confirm(confirm: Optional[str]) -> Optional[str]:
    if confirm is None:
        return None
    return confirm.strip().lower()


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

    args = parser.parse_args()
    confirm = _ensure_confirm(getattr(args, "confirm", None))
    if confirm != "yes":
        _print({"success": False, "error": "写操作已拦截：需要二次确认，请传 --confirm yes"})
        raise SystemExit(2)

    client = BPClient()

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

    _print({"success": False, "error": f"未知命令：{args.command}"})


if __name__ == "__main__":
    main()

