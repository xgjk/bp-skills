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
    parser = argparse.ArgumentParser(description="列出 BP 周期（bp-reporting 统一入口）")
    parser.add_argument("--app-key", default=os.getenv("BP_APP_KEY"), help="BP 系统 appKey（由鉴权层注入）")
    args = parser.parse_args()

    if not args.app_key:
        print(json.dumps({"success": False, "error": "缺少 appKey，请通过 cms-auth-skills 注入或设置 BP_APP_KEY"}, ensure_ascii=False))
        raise SystemExit(2)

    code = _run_reporting_templates(["--list-periods", "--app-key", args.app_key])
    raise SystemExit(code)


if __name__ == "__main__":
    main()

