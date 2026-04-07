#!/usr/bin/env python3
import argparse
import json
from pathlib import Path
from typing import Any, Dict, List


def _resolve_repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


def _resolve_versions_dir(repo_root: Path) -> Path:
    return repo_root / "bp-prototype" / "versions"


def _list_versions(versions_dir: Path) -> List[Dict[str, Any]]:
    if not versions_dir.exists():
        return []

    result: List[Dict[str, Any]] = []
    for d in sorted([p for p in versions_dir.iterdir() if p.is_dir()], key=lambda p: p.name, reverse=True):
        files = sorted([f.name for f in d.iterdir() if f.is_file() and f.suffix.lower() in {".md", ".markdown"}])
        result.append({"versionDir": d.name, "path": str(d), "files": files})
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description="列出 bp-prototype 的模板版本目录与文件清单")
    parser.add_argument("--limit", type=int, default=20, help="最多返回多少个版本目录")
    args = parser.parse_args()

    repo_root = _resolve_repo_root()
    versions_dir = _resolve_versions_dir(repo_root)
    versions = _list_versions(versions_dir)[: max(0, args.limit)]
    print(json.dumps({"success": True, "versionsDir": str(versions_dir), "versions": versions}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

