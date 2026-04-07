#!/usr/bin/env python3
import subprocess
import sys
from pathlib import Path


def _resolve_repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


def main() -> None:
    repo_root = _resolve_repo_root()
    target = repo_root / "bp-prototype" / "scripts" / "generate.py"
    if not target.exists():
        raise SystemExit(f"未找到脚本：{target}")

    proc = subprocess.run([sys.executable, str(target), "--generate"], check=False)
    raise SystemExit(proc.returncode)


if __name__ == "__main__":
    main()

