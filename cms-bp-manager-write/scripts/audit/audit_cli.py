#!/usr/bin/env python3
import json


def main() -> None:
    print(
        json.dumps(
            {
                "success": False,
                "error": "审计入口已迁移至 cms-bp-manager（本技能仅保留纯写入能力）。",
                "nextStep": "请使用：python3 cms-bp-manager/scripts/audit/audit_cli.py <action> [options]",
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()

