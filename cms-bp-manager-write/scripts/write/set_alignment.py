#!/usr/bin/env python3
import argparse
import json
from typing import Any, Dict, List, Optional

from bp_client import BPClient


def _print(obj: Dict[str, Any]) -> None:
    print(json.dumps(obj, ensure_ascii=False, indent=2))


def _ensure_confirm(confirm: Optional[str]) -> Optional[str]:
    if confirm is None:
        return None
    return confirm.strip().lower()


def main() -> None:
    parser = argparse.ArgumentParser(description="对齐/承接关系修改（写操作）")
    parser.add_argument("--action", required=True, choices=["set", "unset", "update"], help="动作：设置/解除/更新")
    parser.add_argument("--source-task-id", required=True, help="下级目标 taskId（发起对齐的一方）")
    parser.add_argument("--target-task-id", required=True, help="上级任务 taskId（被对齐的一方，通常为上级关键举措/关键成果）")
    parser.add_argument("--confirm", required=True, help="二次确认：必须传 yes（即使当前未接入，也保持一致）")
    args = parser.parse_args()

    confirm = _ensure_confirm(args.confirm)
    if confirm != "yes":
        _print({"success": False, "error": "写操作已拦截：需要二次确认，请传 --confirm yes"})
        raise SystemExit(2)

    client = BPClient()
    upward_task_id_list: Optional[List[str]]
    if args.action in {"set", "update"}:
        upward_task_id_list = [args.target_task_id]
    else:
        upward_task_id_list = []

    res = client.AlignTask(current_task_id=args.source_task_id, upward_task_id_list=upward_task_id_list)
    if res.get("resultCode") == 1:
        _print(
            {
                "success": True,
                "data": res.get("data"),
                "message": "对齐关系已更新"
                if args.action in {"set", "update"}
                else "对齐关系已解除（upwardTaskIdList 置空）",
            }
        )
        return
    _print({"success": False, "error": res.get("resultMsg") or "对齐关系更新失败"})
    raise SystemExit(2)


if __name__ == "__main__":
    main()

