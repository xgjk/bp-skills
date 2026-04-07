#!/usr/bin/env python3
import argparse
import json
import os
import subprocess
import sys
from pathlib import Path


def _resolve_repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


def _run_reporting_templates(args: list[str]) -> int:
    repo_root = _resolve_repo_root()
    target = repo_root / "bp-reporting-templates" / "scripts" / "main.py"
    if not target.exists():
        raise FileNotFoundError(f"未找到脚本：{target}")
    proc = subprocess.run([sys.executable, str(target), *args], check=False)
    return proc.returncode


def main() -> None:
    parser = argparse.ArgumentParser(description="生成 BP 填写规范（月报/季报/半年报/年报）（bp-reporting 统一入口）")
    parser.add_argument("request", nargs="?", default="生成BP填写规范", help="自然语言请求（透传给底层生成器）")
    parser.add_argument("--app-key", default=os.getenv("BP_APP_KEY"), help="BP 系统 appKey（由鉴权层注入）")
    parser.add_argument("--period-id", required=True, help="BP 周期 ID")
    parser.add_argument("--template-types", required=True, help="类型：月报,季报,半年报,年报,四套（逗号分隔）")
    parser.add_argument("--org-name", help="组织节点名称（与 group-id 二选一）")
    parser.add_argument("--group-id", help="分组 groupId（与 org-name 二选一）")
    parser.add_argument("--output", default="./output", help="输出目录")
    args = parser.parse_args()

    if not args.app_key:
        print(json.dumps({"success": False, "error": "缺少 appKey，请通过 cms-auth-skills 注入或设置 BP_APP_KEY"}, ensure_ascii=False))
        raise SystemExit(2)

    if not args.org_name and not args.group_id:
        print(json.dumps({"success": False, "error": "缺少组织定位信息：请提供 --org-name 或 --group-id"}, ensure_ascii=False))
        raise SystemExit(2)

    forwarded = [
        args.request,
        "--app-key",
        args.app_key,
        "--period-id",
        args.period_id,
        "--template-types",
        args.template_types,
        "--output",
        args.output,
    ]
    if args.org_name:
        forwarded += ["--org-name", args.org_name]
    if args.group_id:
        forwarded += ["--group-id", args.group_id]

    code = _run_reporting_templates(forwarded)
    raise SystemExit(code)


if __name__ == "__main__":
    main()

