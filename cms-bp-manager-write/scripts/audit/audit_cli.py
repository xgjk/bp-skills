#!/usr/bin/env python3
import argparse
import os
import subprocess
import sys
from pathlib import Path


def _resolve_repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


def _resolve_audit_script() -> Path:
    repo_root = _resolve_repo_root()
    target = repo_root / "bp-audit" / "scripts" / "bp-audit" / "bp_api.py"
    if not target.exists():
        raise FileNotFoundError(f"未找到 bp-audit 脚本：{target}")
    return target


def main() -> None:
    parser = argparse.ArgumentParser(description="bp-manager-write 审计入口（复用 bp-audit）")
    parser.add_argument("action", help="bp-audit 的 action，如 get_all_periods/get_group_tree/get_task_tree/get_goal_detail 等")
    parser.add_argument("--format", default="md", choices=["md", "json"], help="输出格式，默认 md")
    parser.add_argument("--period-id", help="周期ID")
    parser.add_argument("--group-id", help="分组ID")
    parser.add_argument("--task-id", help="任务ID（目标/KR/举措）")
    parser.add_argument("--name", help="搜索关键词（用于 search_group/search_task）")
    parser.add_argument("--only-personal", action="store_true", help="仅个人分组（仅 get_group_tree 时有效）")
    parser.add_argument("--app-key", default=os.getenv("BP_APP_KEY"), help="BP 系统 appKey（由鉴权层注入）")
    args = parser.parse_args()

    audit_script = _resolve_audit_script()

    forwarded = [sys.executable, str(audit_script), args.action, "--format", args.format]
    if args.app_key:
        forwarded += ["--app_key", args.app_key]
    if args.period_id:
        forwarded += ["--period_id", args.period_id]
    if args.group_id:
        forwarded += ["--group_id", args.group_id]
    if args.task_id:
        forwarded += ["--task_id", args.task_id]
    if args.name:
        forwarded += ["--name", args.name]
    if args.only_personal:
        forwarded += ["--only_personal"]

    proc = subprocess.run(forwarded, check=False)
    raise SystemExit(proc.returncode)


if __name__ == "__main__":
    main()

