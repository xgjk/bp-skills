#!/usr/bin/env python3
import argparse
from pathlib import Path


def _resolve_repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


def _resolve_versions_dir(repo_root: Path) -> Path:
    return repo_root / "bp-prototype" / "versions"


def main() -> None:
    parser = argparse.ArgumentParser(description="读取并输出指定版本下的模板文件内容")
    parser.add_argument("--version-dir", required=True, help="版本目录名（位于 bp-prototype/versions/ 下）")
    parser.add_argument("--template-type", required=True, choices=["月报", "季报", "半年报", "年报"], help="模板类型")
    args = parser.parse_args()

    repo_root = _resolve_repo_root()
    versions_dir = _resolve_versions_dir(repo_root)
    target_dir = versions_dir / args.version_dir
    if not target_dir.exists() or not target_dir.is_dir():
        raise SystemExit(f"未找到版本目录：{target_dir}")

    candidates = sorted([p for p in target_dir.iterdir() if p.is_file() and p.suffix.lower() in {'.md', '.markdown'}])
    if not candidates:
        raise SystemExit(f"版本目录下没有找到模板文件：{target_dir}")

    key_map = {"月报": "MONTH", "季报": "QUARTER", "半年报": "HALFYEAR", "年报": "YEAR"}
    key = key_map[args.template_type]
    picked = None
    for p in candidates:
        if key in p.name:
            picked = p
            break

    if not picked:
        raise SystemExit(f"未在版本目录中找到类型为「{args.template_type}」的模板文件（期望文件名包含 {key}）：{target_dir}")

    print(picked.read_text(encoding="utf-8"))


if __name__ == "__main__":
    main()

