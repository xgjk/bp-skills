#!/usr/bin/env python3
import argparse
import json
import sys


def main() -> None:
    parser = argparse.ArgumentParser(description="对齐/承接关系修改（接口接入点占位脚本）")
    parser.add_argument("--action", required=True, choices=["set", "unset", "update"], help="动作：设置/解除/更新")
    parser.add_argument("--source-task-id", required=True, help="下级目标 taskId（发起对齐的一方）")
    parser.add_argument("--target-task-id", required=True, help="上级任务 taskId（被对齐的一方，通常为上级关键举措/关键成果）")
    parser.add_argument("--confirm", required=True, help="二次确认：必须传 yes（即使当前未接入，也保持一致）")
    args = parser.parse_args()

    print(
        json.dumps(
            {
                "success": False,
                "error": "对齐/承接关系修改接口尚未接入（禁止编造 Open API）。",
                "requiredApiContract": {
                    "endpoint": "请提供真实接口路径（例如 /bp/xxx/align 或等价路径）",
                    "method": "GET/POST/PUT/DELETE",
                    "authMode": "appKey 或 access-token（以接口定义为准）",
                    "request": {
                        "sourceTaskId": args.source_task_id,
                        "targetTaskId": args.target_task_id,
                        "action": args.action,
                    },
                    "response": "Result<T> 的 data 结构与错误码说明",
                    "idempotency": "是否幂等、重复设置/解除的返回行为",
                },
                "nextStep": "拿到接口契约后，在本脚本中调用 bp_client 或新增专用 client 方法接入实现，并在 references/workflow/README.md 更新说明。",
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    raise SystemExit(2)


if __name__ == "__main__":
    main()

