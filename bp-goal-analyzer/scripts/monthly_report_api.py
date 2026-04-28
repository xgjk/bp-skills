#!/usr/bin/env python3
"""BP Goal Analyzer — single-goal data collection, judgment, and JSON assembly.

Usage:
    python monthly_report_api.py <action> [options]

Actions:
    collect_goal_progress        Exclusion + progress markdown + black-lamp + reportId extraction
    collect_previous_month_data  Aggregate previous month's reports + evaluations
    split_prev_report_by_goal   Split prev report into per-goal sections for MoM comparison
    build_goal_evidence          Build goal-level evidence ledger with R-code (R{goalSeq}{NNN})
    build_judgment_input         Assemble judgment material package + pre-fill black lamp
    aggregate_lamp_colors        Aggregate action lamp colors -> goal lamp color
    assemble_goal_json           Assemble complete goal JSON from AI fragments + script data
    validate_goal_json           Validate goal_complete.json against v1 schema (13 checks)
    save_task_monthly_reading    Save goal JSON to remote API (2.35)

Environment:
    BP_OPEN_API_APP_KEY       Authentication key (required)
    BP_OPEN_API_BASE_URL      API base URL (optional, has default)
"""

import argparse
import calendar
import json
import os
import re
import shutil
import sys
import time
from datetime import datetime

import requests

BASE_URL = os.environ.get(
    "BP_OPEN_API_BASE_URL",
    "https://sg-al-cwork-web.mediportal.com.cn/open-api",
)
APP_KEY = os.environ.get("BP_OPEN_API_APP_KEY", "")
TIMEOUT = 30
QUERY_RETRY_DELAY_SECONDS = 60
QUERY_MAX_RETRIES = 1


def _log(msg):
    print(f"[progress] {msg}", file=sys.stderr)


def _do_request(method, url, headers, params=None, json_body=None):
    """Execute a single HTTP request and return parsed result."""
    if method == "GET":
        resp = requests.get(url, params=params, headers=headers, timeout=TIMEOUT)
    else:
        req_headers = {**headers, "Content-Type": "application/json"}
        resp = requests.post(url, params=params, json=json_body, headers=req_headers, timeout=TIMEOUT)

    resp.raise_for_status()
    data = resp.json()

    if data.get("resultCode") != 1:
        return {"error": data.get("resultMsg", "Unknown API error"), "resultCode": data.get("resultCode")}

    return {"success": True, "data": data.get("data")}


def _request(method, path, *, params=None, json_body=None):
    if not APP_KEY:
        return {"error": "BP_OPEN_API_APP_KEY is not configured. Set it as an environment variable."}

    url = f"{BASE_URL}{path}"
    headers = {"appKey": APP_KEY}

    for attempt in range(1 + QUERY_MAX_RETRIES):
        try:
            result = _do_request(method, url, headers, params=params, json_body=json_body)
        except requests.HTTPError as e:
            result = {"error": f"HTTP {e.response.status_code}: {e.response.text}",
                      "resultCode": e.response.status_code}
        except Exception as e:
            return {"error": str(e)}

        if result.get("success"):
            return result

        rc = result.get("resultCode")
        is_retryable = rc in (401, 429) or (isinstance(rc, int) and rc >= 500)
        if is_retryable and attempt < QUERY_MAX_RETRIES:
            _log(f"Query got resultCode={rc} on {path}, waiting {QUERY_RETRY_DELAY_SECONDS}s before retry...")
            time.sleep(QUERY_RETRY_DELAY_SECONDS)
            continue

        return result

    return result




def _strip_html(html):
    """Strip HTML tags and convert to plain text. <br> becomes newline."""
    if not html:
        return ""
    text = re.sub(r'<br\s*/?>', '\n', html)
    text = re.sub(r'<[^>]+>', '', text)
    return text.strip()



# ─── Goal detail slimming ─────────────────────────────────────────

_GOAL_DETAIL_FIELDS = (
    "id", "name", "fullLevelNumber", "type",
    "planDateRange", "statusDesc", "measureStandard",
    "supervisorEmpName", "acceptorEmpName",
)

_KR_FIELDS = (
    "id", "name", "fullLevelNumber", "type",
    "planDateRange", "statusDesc", "measureStandard",
    "supervisorEmpName", "acceptorEmpName",
)

_ACTION_FIELDS = (
    "id", "name", "fullLevelNumber", "type",
    "planDateRange", "statusDesc",
    "supervisorEmpName", "acceptorEmpName",
)


def _slim_action(action):
    """Keep only fields needed for lamp judgment on an action node."""
    if not action:
        return action
    slim = {k: action[k] for k in _ACTION_FIELDS if k in action}
    if slim.get("name"):
        slim["name"] = _strip_html(slim["name"])
    return slim


def _slim_kr(kr):
    """Keep only fields needed for gap analysis on a KR node."""
    if not kr:
        return kr
    slim = {k: kr[k] for k in _KR_FIELDS if k in kr}
    if slim.get("name"):
        slim["name"] = _strip_html(slim["name"])
    ms = slim.get("measureStandard", "")
    if ms:
        slim["measureStandard"] = _strip_html(ms)
    action_list = kr.get("actionList") or kr.get("actions") or []
    slim["actionList"] = [_slim_action(a) for a in action_list]
    return slim


def _slim_goal_detail(detail):
    """Keep only fields needed for lamp judgment, strip HTML from measureStandard and name."""
    if not detail:
        return detail
    slim = {k: detail[k] for k in _GOAL_DETAIL_FIELDS if k in detail}
    if slim.get("name"):
        slim["name"] = _strip_html(slim["name"])
    ms = slim.get("measureStandard", "")
    if ms:
        slim["measureStandard"] = _strip_html(ms)
    kr_list = detail.get("keyResultList") or detail.get("keyResults") or []
    slim["keyResultList"] = [_slim_kr(kr) for kr in kr_list]
    return slim


# ─── Working directory helpers ────────────────────────────────────

def _goal_dir(group_id, month, goal_id):
    """Return the per-goal working directory path.

    Fixed: /Users/openclaw-data/bp/{groupId}_{goalId}_{month}/
    """
    return f"/Users/openclaw-data/bp/{group_id}_{goal_id}_{month}"


def _work_dir(group_id, month):
    """Return the group-level working directory path for prev reports.

    Fixed: /Users/openclaw-data/bp/bp_report_{groupId}_{month}/
    """
    return f"/Users/openclaw-data/bp/bp_report_{group_id}_{month}"


def _prepare_goal_dir(group_id, month, goal_id):
    """Ensure standalone goal directory is ready for this run.

    Logic:
    - If directory exists: clear all files/subdirectories.
    - If directory does not exist: create it.
    """
    gd = _goal_dir(group_id, month, goal_id)
    if os.path.isdir(gd):
        import shutil
        for item in os.listdir(gd):
            item_path = os.path.join(gd, item)
            if os.path.isfile(item_path):
                os.remove(item_path)
            elif os.path.isdir(item_path):
                shutil.rmtree(item_path)
        _log(f"Standalone mode: cleared existing directory {gd}")
    else:
        os.makedirs(gd, exist_ok=True)
        _log(f"Standalone mode: created directory {gd}")
    return gd


def _parse_plan_date_range(plan_date_range):
    """Parse 'yyyy-MM-dd ~ yyyy-MM-dd' into (start_str, end_str) or (None, None)."""
    if not plan_date_range or "~" not in plan_date_range:
        return None, None
    parts = plan_date_range.split("~")
    start = parts[0].strip() if len(parts) > 0 else None
    end = parts[1].strip() if len(parts) > 1 else None
    return start or None, end or None


def _extract_goal_seq(full_level_number):
    """Extract goal sequence number from fullLevelNumber like 'P3863-3' -> '3'."""
    if not full_level_number or "-" not in full_level_number:
        return "0"
    return full_level_number.rsplit("-", 1)[-1]


def _judge_exclusion(plan_date_range, status_desc, month):
    """Determine whether a node should be excluded from this month's review.

    Returns: {"excluded": bool, "reason": str | None}
    Rules (hit-and-stop):
    1. statusDesc == "草稿" -> exclude
    2. planStartDate and planEndDate both empty -> exclude
    3. planStartDate > month last day -> exclude
    4. planEndDate < month first day -> exclude
    5. else -> participate
    """
    if status_desc == "草稿":
        return {"excluded": True, "reason": "草稿未正式发布"}

    start_str, end_str = _parse_plan_date_range(plan_date_range)
    if start_str is None and end_str is None:
        return {"excluded": True, "reason": "计划时间范围为空，无法判断是否覆盖本月"}

    year, mon = int(month[:4]), int(month[5:7])
    last_day = calendar.monthrange(year, mon)[1]
    month_first = f"{year:04d}-{mon:02d}-01"
    month_last = f"{year:04d}-{mon:02d}-{last_day:02d}"

    if start_str and start_str > month_last:
        return {"excluded": True, "reason": f"计划开始日期({start_str})晚于本月末({month_last})"}
    if end_str and end_str < month_first:
        return {"excluded": True, "reason": f"计划结束日期({end_str})早于本月初({month_first})"}

    return {"excluded": False, "reason": None}


_BLACK_LAMP_PLACEHOLDERS = [
    "# 汇报推进各情况总结",
    "暂无汇报推进记录",
    "暂无汇报推进记录。",
    "暂无汇报",
    "暂无汇报。",
    "无推进记录",
    "无推进记录。",
    "暂无推进记录",
    "暂无推进记录。",
    "无汇报内容",
    "无汇报内容。",
]


def _judge_black_lamp(progress_markdown):
    """Check if an action has no valid evidence (black lamp).

    Returns True when progressMarkdown is empty, whitespace-only,
    or contains only placeholder text with no substantive content.
    """
    if not progress_markdown or not progress_markdown.strip():
        return True
    stripped = progress_markdown.strip()
    for placeholder in _BLACK_LAMP_PLACEHOLDERS:
        if stripped == placeholder:
            return True
    content_without_headings = re.sub(r'^#{1,6}\s+.*$', '', stripped, flags=re.MULTILINE).strip()
    if not content_without_headings:
        return True
    for placeholder in _BLACK_LAMP_PLACEHOLDERS:
        if content_without_headings == placeholder:
            return True
    return False


def _extract_reports_from_markdown(markdown):
    """Extract report metadata from getReportProgressMarkdown aggregated Markdown.

    Returns: [{"reportId": "123", "title": "...", "authorId": "..."}, ...]
    """
    if not markdown:
        return []
    reports = []
    sections = re.split(r'^---$', markdown, flags=re.MULTILINE)
    for section in sections:
        rid_match = re.search(r'- 汇报ID：(\d+)', section)
        if rid_match:
            title_match = re.search(r'^## (.+)$', section, re.MULTILINE)
            author_match = re.search(r'- 汇报人ID：(\d+)', section)
            reports.append({
                "reportId": rid_match.group(1),
                "title": title_match.group(1).strip() if title_match else "",
                "authorId": author_match.group(1) if author_match else "",
            })
    return reports


# ─── init_work_dir ───────────────────────────────────────────────

def collect_goal_progress(args):
    """[Phase 2-3] For a single goal: exclusion check + fetch evidence Markdown + black lamp + reportId extraction.

    Replaces collect_goal_data in the new flow. Uses getReportProgressMarkdown (2.34)
    instead of fetching individual reports.

    Outputs: goals/{goalId}/progress.json with structure, exclusion state,
    progressMarkdown per action/KR, and extracted reportIds.
    """
    if not args.goal_id:
        return {"error": "goal_id is required for collect_goal_progress"}
    if not args.group_id:
        return {"error": "group_id is required for collect_goal_progress"}
    if not args.month:
        return {"error": "month (YYYY-MM) is required for collect_goal_progress"}

    _prepare_goal_dir(args.group_id, args.month, args.goal_id)

    errors = []

    _log(f"Fetching goal detail: {args.goal_id}")
    detail = _request("GET", "/bp/task/v2/getGoalAndKeyResult", params={"id": args.goal_id})
    if not detail.get("success"):
        return {"error": f"Failed to fetch goal detail: {detail.get('error')}"}

    goal_detail_raw = detail["data"]
    goal_detail = _slim_goal_detail(goal_detail_raw)

    goal_exclusion = _judge_exclusion(
        goal_detail.get("planDateRange", ""),
        goal_detail.get("statusDesc", ""),
        args.month,
    )

    if goal_exclusion["excluded"]:
        _log(f"Goal {args.goal_id} excluded: {goal_exclusion['reason']}")
        output = {
            "goalId": args.goal_id,
            "groupId": args.group_id,
            "month": args.month,
            "goalDetail": goal_detail,
            "excluded": True,
            "excludeReason": goal_exclusion["reason"],
            "krData": {},
            "actionData": {},
        }
    else:
        kr_data = {}
        action_data = {}
        all_report_ids = set()

        kr_list = goal_detail_raw.get("keyResultList") or goal_detail_raw.get("keyResults") or []
        for kr in kr_list:
            kr_id = str(kr.get("id", ""))
            if not kr_id:
                continue

            kr_exclusion = _judge_exclusion(
                kr.get("planDateRange", ""),
                kr.get("statusDesc", ""),
                args.month,
            )

            kr_md = ""
            kr_reports = []
            if not kr_exclusion["excluded"]:
                _log(f"  Fetching progress markdown for KR {kr_id}")
                md_result = _request("GET", "/bp/task/reportProgress",
                                     params={"taskId": kr_id, "month": args.month})
                if md_result.get("success"):
                    kr_md = md_result.get("data", "") or ""
                    kr_reports = _extract_reports_from_markdown(kr_md)
                    for r in kr_reports:
                        all_report_ids.add(r["reportId"])
                else:
                    errors.append({"step": "kr_progress", "id": kr_id, "error": md_result.get("error")})

            slim_kr = _slim_kr(kr)
            kr_data[kr_id] = {
                "name": _strip_html(kr.get("name", "")),
                "fullLevelNumber": kr.get("fullLevelNumber", ""),
                "measureStandard": slim_kr.get("measureStandard", ""),
                "planDateRange": kr.get("planDateRange", ""),
                "statusDesc": kr.get("statusDesc", ""),
                "excluded": kr_exclusion["excluded"],
                "excludeReason": kr_exclusion.get("reason"),
                "progressMarkdown": kr_md,
                "reportIds": [r["reportId"] for r in kr_reports],
                "reports": kr_reports,
            }

            action_list = kr.get("actionList") or kr.get("actions") or []
            for action in action_list:
                action_id = str(action.get("id", ""))
                if not action_id:
                    continue

                action_exclusion = _judge_exclusion(
                    action.get("planDateRange", ""),
                    action.get("statusDesc", ""),
                    args.month,
                )
                # 父 KR 被排除时，举措同样标记为排除
                if not action_exclusion["excluded"] and kr_exclusion["excluded"]:
                    action_exclusion = {
                        "excluded": True,
                        "reason": f"父KR({kr.get('fullLevelNumber', kr_id)})已被排除：{kr_exclusion.get('reason', '')}",
                    }

                action_md = ""
                action_reports = []
                is_black = False
                if not action_exclusion["excluded"]:
                    _log(f"  Fetching progress markdown for action {action_id}")
                    md_result = _request("GET", "/bp/task/reportProgress",
                                         params={"taskId": action_id, "month": args.month})
                    if md_result.get("success"):
                        action_md = md_result.get("data", "") or ""
                        action_reports = _extract_reports_from_markdown(action_md)
                        for r in action_reports:
                            all_report_ids.add(r["reportId"])
                        is_black = _judge_black_lamp(action_md)
                    else:
                        errors.append({"step": "action_progress", "id": action_id, "error": md_result.get("error")})
                        is_black = True

                action_data[action_id] = {
                    "name": _strip_html(action.get("name", "")),
                    "fullLevelNumber": action.get("fullLevelNumber", ""),
                    "parentKrId": kr_id,
                    "planDateRange": action.get("planDateRange", ""),
                    "statusDesc": action.get("statusDesc", ""),
                    "excluded": action_exclusion["excluded"],
                    "excludeReason": action_exclusion.get("reason"),
                    "isBlackLamp": is_black,
                    "progressMarkdown": action_md,
                    "reportIds": [r["reportId"] for r in action_reports],
                    "reports": action_reports,
                }

        output = {
            "goalId": args.goal_id,
            "groupId": args.group_id,
            "month": args.month,
            "goalDetail": goal_detail,
            "excluded": False,
            "excludeReason": None,
            "krData": kr_data,
            "actionData": action_data,
            "allReportIds": sorted(all_report_ids),
            "stats": {
                "krCount": len(kr_data),
                "actionCount": len(action_data),
                "uniqueReportCount": len(all_report_ids),
                "excludedKrCount": sum(1 for v in kr_data.values() if v["excluded"]),
                "excludedActionCount": sum(1 for v in action_data.values() if v["excluded"]),
                "blackLampActionCount": sum(1 for v in action_data.values() if v.get("isBlackLamp")),
            },
        }

    if errors:
        output["errors"] = errors

    gd = _goal_dir(args.group_id, args.month, args.goal_id)
    os.makedirs(gd, exist_ok=True)
    output_path = args.output or os.path.join(gd, "progress.json")
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    _log(f"Done! Goal progress written to {output_path}")
    return {"success": True, "outputFile": output_path, "excluded": output["excluded"],
            "stats": output.get("stats", {})}


# ─── build_goal_evidence (Phase 3.5) ─────────────────────────────

def build_goal_evidence(args):
    """[Phase 3.5] Build goal-level evidence ledger with R-code assignment.

    Reads progress.json for a goal, deduplicates reports, assigns R-codes,
    determines evidence level (primary/secondary), and writes goal_evidence.md.
    """
    if not args.goal_id:
        return {"error": "goal_id is required for build_goal_evidence"}
    if not args.group_id:
        return {"error": "group_id is required for build_goal_evidence"}
    if not args.month:
        return {"error": "month (YYYY-MM) is required for build_goal_evidence"}

    employee_id = getattr(args, "employee_id", None) or ""

    gd = _goal_dir(args.group_id, args.month, args.goal_id)
    progress_path = os.path.join(gd, "progress.json")
    if not os.path.isfile(progress_path):
        return {"error": f"progress.json not found: {progress_path}. Run collect_goal_progress first."}

    with open(progress_path, "r", encoding="utf-8") as f:
        progress = json.load(f)

    goal_detail = progress.get("goalDetail", {})
    goal_seq = _extract_goal_seq(goal_detail.get("fullLevelNumber", ""))

    if progress.get("excluded"):
        md = f"## 目标: {goal_detail.get('name', '')} 证据台账\n\n> 该目标不参与本月自查，无证据台账。\n"
        output_path = os.path.join(gd, "goal_evidence.md")
        with open(output_path, "w", encoding="utf-8") as f:
            f.write(md)
        return {"success": True, "outputFile": output_path, "rCodeCount": 0}

    seen_report_ids = {}
    node_report_map = {}

    def _is_primary_evidence(author_id):
        if not employee_id:
            return True
        author = str(author_id or "").strip()
        if not author:
            return True
        return author == str(employee_id).strip()

    for kr_id, kr_info in progress.get("krData", {}).items():
        if kr_info.get("excluded"):
            continue
        for r in kr_info.get("reports", []):
            rid = r["reportId"]
            if rid not in seen_report_ids:
                seen_report_ids[rid] = {
                    "reportId": rid,
                    "title": r.get("title", ""),
                    "authorId": r.get("authorId", ""),
                    "level": "主证据" if _is_primary_evidence(r.get("authorId")) else "辅证",
                    "rCode": None,
                    "nodes": [],
                }
            seen_report_ids[rid]["nodes"].append({
                "nodeId": kr_id,
                "nodeName": kr_info.get("name", ""),
                "nodeNumber": kr_info.get("fullLevelNumber", ""),
                "nodeType": "关键成果",
            })
            node_report_map.setdefault(kr_id, []).append(rid)

    for action_id, action_info in progress.get("actionData", {}).items():
        if action_info.get("excluded"):
            continue
        for r in action_info.get("reports", []):
            rid = r["reportId"]
            if rid not in seen_report_ids:
                seen_report_ids[rid] = {
                    "reportId": rid,
                    "title": r.get("title", ""),
                    "authorId": r.get("authorId", ""),
                    "level": "主证据" if _is_primary_evidence(r.get("authorId")) else "辅证",
                    "rCode": None,
                    "nodes": [],
                }
            seen_report_ids[rid]["nodes"].append({
                "nodeId": action_id,
                "nodeName": action_info.get("name", ""),
                "nodeNumber": action_info.get("fullLevelNumber", ""),
                "nodeType": "举措",
            })
            node_report_map.setdefault(action_id, []).append(rid)

    r_index = 1
    r_code_map = {}
    for rid in sorted(seen_report_ids.keys()):
        r_code = f"R{goal_seq}{r_index:03d}"
        seen_report_ids[rid]["rCode"] = r_code
        r_code_map[rid] = r_code
        r_index += 1

    goal_name = _strip_html(progress["goalDetail"].get("name", ""))
    goal_number = progress["goalDetail"].get("fullLevelNumber", "")
    primary_count = sum(1 for v in seen_report_ids.values() if v["level"] == "主证据")
    secondary_count = sum(1 for v in seen_report_ids.values() if v["level"] == "辅证")

    lines = [
        f"## 目标 {goal_number}: {goal_name} 证据台账\n",
        "### 证据概览",
        f"- 有效汇报总数：{len(seen_report_ids)} 份（去重后）",
        f"- 其中本人主证据：{primary_count} 份、他人辅证：{secondary_count} 份\n",
        "### R 编号索引",
        "| R 编号 | 汇报标题 | 证据级别 | 汇报链接 | 关联节点 |",
        "|--------|---------|---------|---------|---------|",
    ]
    for rid in sorted(seen_report_ids.keys()):
        info = seen_report_ids[rid]
        nodes_str = " / ".join(
            f"{n['nodeNumber']} {_strip_html(n['nodeName'])}" for n in info["nodes"]
        )
        lines.append(
            f"| {info['rCode']} | 《{_strip_html(info['title'])}》 | {info['level']} "
            f"| [查看汇报](huibao://view?id={rid}) | {nodes_str} |"
        )

    lines.append("")
    lines.append("### 按节点归集")

    for kr_id, kr_info in progress.get("krData", {}).items():
        if kr_info.get("excluded"):
            continue
        kr_own_rids = list(dict.fromkeys(node_report_map.get(kr_id, [])))

        child_rids = []
        for action_id, action_info in progress.get("actionData", {}).items():
            if action_info.get("excluded") or action_info.get("parentKrId") != kr_id:
                continue
            child_rids.extend(node_report_map.get(action_id, []))
        all_kr_rids = list(dict.fromkeys(kr_own_rids + child_rids))

        r_codes = [r_code_map[rid] for rid in all_kr_rids if rid in r_code_map]
        has_primary = any(seen_report_ids[rid]["level"] == "主证据" for rid in all_kr_rids if rid in seen_report_ids)
        sufficiency = "充分" if has_primary else ("基本充分" if r_codes else "无")
        kr_name = _strip_html(kr_info.get('name', ''))
        lines.append(f"#### KR {kr_info.get('fullLevelNumber', '')}: {kr_name}")
        lines.append(f"- 关联证据：{', '.join(r_codes) if r_codes else '无'}")
        lines.append(f"- 证据充分性：{sufficiency}")

        for action_id, action_info in progress.get("actionData", {}).items():
            if action_info.get("excluded") or action_info.get("parentKrId") != kr_id:
                continue
            a_rids = list(dict.fromkeys(node_report_map.get(action_id, [])))
            a_r_codes = [r_code_map[rid] for rid in a_rids if rid in r_code_map]
            a_has_primary = any(seen_report_ids[rid]["level"] == "主证据" for rid in a_rids if rid in seen_report_ids)
            a_sufficiency = "充分" if a_has_primary else ("基本充分" if a_r_codes else "无")
            is_black = action_info.get("isBlackLamp", False)
            action_name = _strip_html(action_info.get('name', ''))
            lines.append(f"#### 举措 {action_info.get('fullLevelNumber', '')}: {action_name}")
            lines.append(f"- 关联证据：{', '.join(a_r_codes) if a_r_codes else '无'}")
            lines.append(f"- 证据充分性：{a_sufficiency}")
            if is_black:
                lines.append("- 黑灯标记：是")
        lines.append("")

    md_content = "\n".join(lines)
    output_path = os.path.join(gd, "goal_evidence.md")
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(md_content)

    evidence_json = {
        "goalId": args.goal_id,
        "rCodeMap": {rid: info["rCode"] for rid, info in seen_report_ids.items()},
        "reports": {rid: info for rid, info in seen_report_ids.items()},
        "nodeReportMap": node_report_map,
    }
    evidence_json_path = os.path.join(gd, "goal_evidence.json")
    with open(evidence_json_path, "w", encoding="utf-8") as f:
        json.dump(evidence_json, f, ensure_ascii=False, indent=2)

    last_r = f"R{goal_seq}{r_index - 1:03d}" if r_index > 1 else "N/A"
    _log(f"Done! Goal evidence ledger written to {output_path} ({len(seen_report_ids)} reports, R{goal_seq}001-{last_r})")
    return {
        "success": True, "outputFile": output_path, "evidenceJsonFile": evidence_json_path,
        "rCodeCount": len(seen_report_ids),
    }


# ─── build_judgment_input (Phase 4) ──────────────────────────────

def build_judgment_input(args):
    """[Phase 4] Assemble judgment material package Markdown for each action under a goal.

    Reads progress.json + goal_evidence.json, generates a Markdown package per action
    containing BP anchor info, evidence Markdown, R-codes, and KR measurement standard.
    """
    if not args.goal_id:
        return {"error": "goal_id is required for build_judgment_input"}
    if not args.group_id:
        return {"error": "group_id is required for build_judgment_input"}
    if not args.month:
        return {"error": "month (YYYY-MM) is required for build_judgment_input"}

    gd = _goal_dir(args.group_id, args.month, args.goal_id)
    progress_path = os.path.join(gd, "progress.json")
    evidence_json_path = os.path.join(gd, "goal_evidence.json")

    if not os.path.isfile(progress_path):
        return {"error": f"progress.json not found: {progress_path}"}
    if not os.path.isfile(evidence_json_path):
        return {"error": f"goal_evidence.json not found: {evidence_json_path}"}

    with open(progress_path, "r", encoding="utf-8") as f:
        progress = json.load(f)
    with open(evidence_json_path, "r", encoding="utf-8") as f:
        evidence = json.load(f)

    if progress.get("excluded"):
        return {"success": True, "message": "Goal excluded, no judgment input needed.", "files": []}

    r_code_map = evidence.get("rCodeMap", {})
    node_report_map = evidence.get("nodeReportMap", {})
    goal_detail = progress.get("goalDetail", {})

    files = []
    black_lamp_prefills = []

    for action_id, action_info in progress.get("actionData", {}).items():
        if action_info.get("excluded"):
            continue
        if action_info.get("isBlackLamp"):
            black_lamp_prefills.append({
                "actionId": action_id,
                "actionName": _strip_html(action_info.get("name", "")),
                "fullLevelNumber": action_info.get("fullLevelNumber", ""),
                "lamp": "black",
                "reason": "无汇报记录，自动标记为黑灯",
            })
            continue

        parent_kr_id = action_info.get("parentKrId", "")
        kr_info = progress.get("krData", {}).get(parent_kr_id, {})

        action_rids = list(dict.fromkeys(node_report_map.get(action_id, [])))
        action_r_codes = [f"{r_code_map[rid]}(huibao://view?id={rid})" for rid in action_rids if rid in r_code_map]

        action_name = _strip_html(action_info.get('name', ''))
        goal_name = _strip_html(goal_detail.get('name', ''))
        kr_name = _strip_html(kr_info.get('name', ''))
        kr_measure = _strip_html(kr_info.get('measureStandard', '未设置'))

        lines = [
            f"# 判灯材料包：{action_info.get('fullLevelNumber', '')} {action_name}",
            "",
            "## BP 锚点",
            f"- 目标：{goal_detail.get('fullLevelNumber', '')} {goal_name}",
            f"- 所属 KR：{kr_info.get('fullLevelNumber', '')} {kr_name}",
            f"- KR 衡量标准：{kr_measure}",
            f"- 举措编号：{action_info.get('fullLevelNumber', '')}",
            f"- 举措名称：{action_name}",
            f"- 计划时间：{action_info.get('planDateRange', '未设置')}",
            f"- 当前状态：{action_info.get('statusDesc', '')}",
            "",
            f"## 关联证据 R 编号",
            ", ".join(action_r_codes) if action_r_codes else "无关联证据",
            "",
            "## BP下汇报情况",
            "",
            action_info.get("progressMarkdown", "") or "（无汇报内容）",
        ]

        md_content = "\n".join(lines)
        fname = f"judgment_input_{action_id}.md"
        fpath = os.path.join(gd, fname)
        with open(fpath, "w", encoding="utf-8") as f:
            f.write(md_content)
        files.append(fpath)

    if black_lamp_prefills:
        prefill_path = os.path.join(gd, "black_lamp_prefills.json")
        with open(prefill_path, "w", encoding="utf-8") as f:
            json.dump({"actionJudgments": black_lamp_prefills}, f, ensure_ascii=False, indent=2)
        _log(f"Pre-filled {len(black_lamp_prefills)} black lamp actions to {prefill_path}")

    _log(f"Done! {len(files)} judgment input files written, {len(black_lamp_prefills)} black lamp pre-filled")
    return {
        "success": True, "files": files, "count": len(files),
        "blackLampCount": len(black_lamp_prefills),
        "blackLampPrefillFile": os.path.join(gd, "black_lamp_prefills.json") if black_lamp_prefills else None,
    }


# ─── aggregate_lamp_colors (Phase 7) ─────────────────────────────

def aggregate_lamp_colors(args):
    """[Phase 7] Aggregate action lamp colors to goal-level lamp color.

    Reads action_judgments.json (produced by AI in Phase 5-6, containing per-action lamp colors),
    applies goal-level aggregation rule: red > yellow > black > green.
    """
    if not args.goal_id:
        return {"error": "goal_id is required for aggregate_lamp_colors"}
    if not args.group_id:
        return {"error": "group_id is required for aggregate_lamp_colors"}
    if not args.month:
        return {"error": "month (YYYY-MM) is required for aggregate_lamp_colors"}

    gd = _goal_dir(args.group_id, args.month, args.goal_id)
    judgments_path = os.path.join(gd, "action_judgments.json")
    if not os.path.isfile(judgments_path):
        return {"error": f"action_judgments.json not found: {judgments_path}. AI must produce this file in Phase 5."}

    with open(judgments_path, "r", encoding="utf-8") as f:
        raw = json.load(f)

    if isinstance(raw, dict) and "actionJudgments" in raw:
        judgments = {}
        for item in raw["actionJudgments"]:
            aid = str(item.get("actionId", ""))
            if aid:
                judgments[aid] = item
    elif isinstance(raw, list):
        judgments = {}
        for item in raw:
            aid = str(item.get("actionId", ""))
            if aid:
                judgments[aid] = item
    else:
        judgments = raw

    lamp_priority = {"red": 4, "yellow": 3, "black": 2, "green": 1}
    lamp_names = {"red": "🔴", "yellow": "🟡", "black": "⚫", "green": "🟢"}

    highest = "green"
    counts = {"green": 0, "yellow": 0, "red": 0, "black": 0}
    participating_count = 0

    for action_id, info in judgments.items():
        if not isinstance(info, dict):
            continue
        lamp = info.get("lamp") or info.get("color") or "green"
        lamp = lamp.lower().strip()
        if lamp not in lamp_priority:
            _log(f"Unknown lamp value '{lamp}' for action {action_id}, defaulting to green")
            lamp = "green"
        counts[lamp] = counts.get(lamp, 0) + 1
        participating_count += 1
        if lamp_priority.get(lamp, 0) > lamp_priority.get(highest, 0):
            highest = lamp

    if participating_count == 0:
        highest = "black"
        _log("No participating actions found, goal lamp set to black")

    result = {
        "goalId": args.goal_id,
        "goalLamp": highest,
        "goalLampEmoji": lamp_names.get(highest, ""),
        "actionCounts": counts,
        "participatingActionCount": participating_count,
    }

    output_path = os.path.join(gd, "goal_lamp.json")
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    _log(f"Done! Goal lamp: {lamp_names[highest]} ({highest}), actionCounts={counts}, participating={participating_count}")
    return {"success": True, **result, "outputFile": output_path}


# ─── build_evidence_ledger (Phase 8) ─────────────────────────────

def save_task_monthly_reading(args):
    """Save goal monthly reading content via /bp/task/monthlyReading/save (API 2.35).

    Supports two content sources (priority: content_file > content):
    - --content_file: read from file (for participating goals with goal_report.md)
    - --content: inline string (for excluded goals with a short note)
    """
    task_id = getattr(args, "task_id", None)
    if not task_id:
        return {"error": "task_id is required for save_task_monthly_reading"}
    if not args.month:
        return {"error": "month (YYYY-MM) is required for save_task_monthly_reading"}
    if not APP_KEY:
        return {"error": "BP_OPEN_API_APP_KEY is not configured."}

    content = None
    content_file = getattr(args, "content_file", None)
    content_inline = getattr(args, "content", None)

    if content_file:
        if not os.path.isfile(content_file):
            return {"error": f"Content file not found: {content_file}"}
        with open(content_file, "r", encoding="utf-8") as f:
            content = f.read()
    elif content_inline:
        content = content_inline
    else:
        return {"error": "Either --content_file or --content is required for save_task_monthly_reading"}

    if not content.strip():
        return {"error": "Content is empty"}

    body = {
        "taskId": task_id,
        "month": args.month,
        "content": content,
    }

    _log(f"Saving task monthly reading: taskId={task_id}, month={args.month}, chars={len(content)}")
    result = _request("POST", "/bp/task/monthlyReading/save", json_body=body)

    if result.get("success"):
        _log(f"Task monthly reading saved. taskId={task_id}, month={args.month}")

    return result


def collect_previous_month_data(args):
    """Aggregate previous month's reports + evaluations as reference for current month.

    1. Call 2.31 listMonthlyReports — get reportTypeDesc + reportRecordId for previous month
    2. For each reportRecordId, fetch report content via work-report API
    3. Call 2.32 getMonthlyEvaluation — get translated Markdown (self + manager)
    4. Write aggregated JSON to --output file
    """
    if not args.group_id:
        return {"error": "group_id is required for collect_previous_month_data"}
    if not args.month:
        return {"error": "month (YYYY-MM, the previous month) is required for collect_previous_month_data"}

    errors = []
    prev_month = args.month

    # Step 1: list monthly reports for previous month
    _log(f"Fetching monthly report list for {prev_month}...")
    reports_result = _request("GET", "/bp/monthly/report/listByMonth",
                              params={"groupId": args.group_id, "reportMonth": prev_month})

    report_items = []
    if reports_result.get("success"):
        report_items = reports_result.get("data") or []
        _log(f"Found {len(report_items)} report(s) for {prev_month}")
    else:
        errors.append({"step": "list_monthly_reports", "error": reports_result.get("error")})

    # Step 2: fetch report content for each reportRecordId
    # Full text goes to prev_reports/ subdir inside current month work dir; JSON only keeps preview + charCount
    report_month = getattr(args, "report_month", None) or getattr(args, "month", "") or ""
    goal_id = getattr(args, "goal_id", None)
    if goal_id and report_month:
        wd = _goal_dir(args.group_id, report_month, goal_id)
    elif report_month:
        wd = _work_dir(args.group_id, report_month)
    else:
        wd = _work_dir(args.group_id, args.group_id)
    reports_dir = os.path.join(wd, "prev_reports")
    os.makedirs(reports_dir, exist_ok=True)

    report_contents = []
    for item in report_items:
        rid = item.get("reportRecordId")
        type_desc = item.get("reportTypeDesc", "")
        if not rid:
            continue
        rid_str = str(rid)
        _log(f"Fetching report content: {type_desc} (id={rid_str})")
        content_result = _request("GET", "/work-report/report/info", params={"reportId": rid_str})
        if content_result.get("success") and content_result.get("data"):
            rd = content_result["data"]
            content_html = rd.get("contentHtml") or rd.get("content") or ""
            plain_text = _strip_html(content_html)

            report_path = os.path.join(reports_dir, f"prev_{rid_str}.json")
            if not os.path.exists(report_path):
                with open(report_path, "w", encoding="utf-8") as f:
                    json.dump({
                        "reportId": rid_str,
                        "title": rd.get("main", ""),
                        "content": plain_text,
                        "contentHtml": content_html,
                        "createTime": rd.get("createTime"),
                    }, f, ensure_ascii=False, indent=2)

            report_contents.append({
                "reportTypeDesc": type_desc,
                "reportRecordId": rid_str,
                "title": rd.get("main", ""),
                "charCount": len(plain_text),
                "contentPreview": plain_text[:500],
                "createTime": rd.get("createTime"),
            })
        else:
            errors.append({"step": "report_content", "id": rid_str, "error": content_result.get("error")})

    # Step 3: fetch monthly evaluation Markdown
    _log(f"Fetching monthly evaluation for {prev_month}...")
    eval_result = _request("GET", "/bp/monthly/evaluation/query",
                           params={"groupId": args.group_id, "evaluationMonth": prev_month})

    evaluations = []
    if eval_result.get("success"):
        evaluations = eval_result.get("data") or []
        _log(f"Found {len(evaluations)} evaluation(s) for {prev_month}")
    else:
        errors.append({"step": "monthly_evaluation", "error": eval_result.get("error")})

    # Step 4: build output
    output = {
        "groupId": args.group_id,
        "previousMonth": prev_month,
        "collectTime": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "reports": report_contents,
        "evaluations": evaluations,
        "stats": {
            "reportCount": len(report_contents),
            "evaluationCount": len(evaluations),
        },
    }
    if errors:
        output["errors"] = errors

    default_path = os.path.join(wd, "prev_month.json")
    output_path = args.output or default_path
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    _log(f"Done! Previous month data written to {output_path}")
    return {"success": True, "outputFile": output_path, "stats": output["stats"]}


# ─── split_prev_report_by_goal ────────────────────────────────────

def split_prev_report_by_goal(args):
    """Split previous month's full report into per-goal Markdown sections.

    Reads prev_reports/*.json (full report content), locates each goal section
    by heading pattern like '##### P12717-2｜' and writes to prev_goal_sections/{goalId}.md.
    """
    if not args.group_id:
        return {"error": "group_id is required for split_prev_report_by_goal"}
    if not args.month:
        return {"error": "month (YYYY-MM) is required for split_prev_report_by_goal"}
    if not args.goal_id:
        return {"error": "goal_id is required for split_prev_report_by_goal"}

    gd = _goal_dir(args.group_id, args.month, args.goal_id)
    wd = gd

    progress_path = os.path.join(gd, "progress.json")
    if not os.path.isfile(progress_path):
        return {"error": f"progress.json not found: {progress_path}"}

    with open(progress_path, "r", encoding="utf-8") as f:
        progress = json.load(f)

    goal_detail = progress.get("goalDetail", {})
    full_level_number = goal_detail.get("fullLevelNumber", "")
    if not full_level_number:
        return {"error": "fullLevelNumber not found in goalDetail"}

    prev_reports_dir = os.path.join(wd, "prev_reports")
    if not os.path.isdir(prev_reports_dir):
        _log(f"No prev_reports directory found at {prev_reports_dir}, skipping split")
        output_path = os.path.join(gd, "prev_goal_section.md")
        with open(output_path, "w", encoding="utf-8") as f:
            f.write("首月汇报，无上月参考基线。\n")
        return {"success": True, "outputFile": output_path, "hasBaseline": False}

    full_text_parts = []
    for fname in sorted(os.listdir(prev_reports_dir)):
        if not fname.endswith(".json"):
            continue
        fpath = os.path.join(prev_reports_dir, fname)
        with open(fpath, "r", encoding="utf-8") as f:
            rd = json.load(f)
        content = rd.get("content", "")
        if content:
            full_text_parts.append(content)

    if not full_text_parts:
        output_path = os.path.join(gd, "prev_goal_section.md")
        with open(output_path, "w", encoding="utf-8") as f:
            f.write("首月汇报，无上月参考基线。\n")
        return {"success": True, "outputFile": output_path, "hasBaseline": False}

    full_text = "\n\n---\n\n".join(full_text_parts)

    escaped_number = re.escape(full_level_number)
    pattern = re.compile(
        rf'^(#{{1,6}}\s+{escaped_number}[｜|])',
        re.MULTILINE,
    )

    match = pattern.search(full_text)
    if not match:
        _log(f"Goal section heading '{full_level_number}' not found in previous report")
        output_path = os.path.join(gd, "prev_goal_section.md")
        with open(output_path, "w", encoding="utf-8") as f:
            f.write(f"上月报告中未找到目标 {full_level_number} 的章节内容。\n")
        return {"success": True, "outputFile": output_path, "hasBaseline": False}

    start = match.start()
    heading_level = len(match.group(1).split()[0])
    # 下一个同级或更高级（即 # 数量 <= heading_level）的标题为截止边界
    next_heading = re.compile(rf'^#{{1,{heading_level}}}\s', re.MULTILINE)
    rest = full_text[match.end():]
    next_match = next_heading.search(rest)
    if next_match:
        end = match.end() + next_match.start()
        section = full_text[start:end].rstrip()
    else:
        section = full_text[start:].rstrip()

    output_path = os.path.join(gd, "prev_goal_section.md")
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(section)

    _log(f"Done! Extracted prev goal section for {full_level_number}: {len(section)} chars")
    return {"success": True, "outputFile": output_path, "hasBaseline": True, "charCount": len(section)}


# ─── assemble_goal_json ──────────────────────────────────────────

def assemble_goal_json(args):
    """Assemble the complete goal-level JSON from AI fragments + script data.

    Reads progress.json, goal_evidence.json, goal_lamp.json, action_judgments.json,
    kr_analysis.json, goal_summary.json, and merges into goal_complete.json.
    """
    if not args.goal_id:
        return {"error": "goal_id is required for assemble_goal_json"}
    if not args.group_id:
        return {"error": "group_id is required for assemble_goal_json"}
    if not args.month:
        return {"error": "month (YYYY-MM) is required for assemble_goal_json"}

    gd = _goal_dir(args.group_id, args.month, args.goal_id)

    def _load(filename, required=True):
        path = os.path.join(gd, filename)
        if not os.path.isfile(path):
            if required:
                return None, f"{filename} not found: {path}"
            return {}, None
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f), None

    progress, err = _load("progress.json")
    if err:
        return {"error": err}

    if progress.get("excluded"):
        goal_detail = progress.get("goalDetail", {})
        excluded_json = {
            "$schema": "goal_analysis_v1",
            "goalId": str(args.goal_id),
            "groupId": str(args.group_id),
            "month": args.month,
            "goalInfo": {
                "fullLevelNumber": goal_detail.get("fullLevelNumber", ""),
                "name": goal_detail.get("name", ""),
                "planDateRange": goal_detail.get("planDateRange", ""),
                "statusDesc": goal_detail.get("statusDesc", ""),
                "measureStandard": goal_detail.get("measureStandard", ""),
                "excluded": True,
                "excludeReason": progress.get("excludeReason", ""),
            },
        }
        output_path = os.path.join(gd, "goal_complete.json")
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(excluded_json, f, ensure_ascii=False, indent=2)
        _log(f"Excluded goal JSON assembled: {output_path}")
        return {"success": True, "outputFile": output_path, "excluded": True}

    evidence_json, err = _load("goal_evidence.json")
    if err:
        return {"error": err}
    lamp_json, err = _load("goal_lamp.json")
    if err:
        return {"error": err}
    action_judgments, err = _load("action_judgments.json")
    if err:
        return {"error": err}
    kr_analysis, err = _load("kr_analysis.json")
    if err:
        return {"error": err}
    goal_summary, err = _load("goal_summary.json")
    if err:
        return {"error": err}

    if isinstance(action_judgments, dict) and "actionJudgments" in action_judgments:
        aj_map = {}
        for item in action_judgments["actionJudgments"]:
            aid = str(item.get("actionId", ""))
            if aid:
                aj_map[aid] = item
        action_judgments = aj_map
    elif isinstance(action_judgments, list):
        aj_map = {}
        for item in action_judgments:
            aid = str(item.get("actionId", ""))
            if aid:
                aj_map[aid] = item
        action_judgments = aj_map

    black_prefills, _ = _load("black_lamp_prefills.json", required=False)
    if black_prefills and "actionJudgments" in black_prefills:
        for item in black_prefills["actionJudgments"]:
            aid = str(item.get("actionId", ""))
            if aid and aid not in action_judgments:
                action_judgments[aid] = item

    kr_analysis_map = {}
    if isinstance(kr_analysis, list):
        for item in kr_analysis:
            kid = str(item.get("krId", ""))
            if kid:
                kr_analysis_map[kid] = item
    elif isinstance(kr_analysis, dict) and "krAnalysis" in kr_analysis:
        for item in kr_analysis["krAnalysis"]:
            kid = str(item.get("krId", ""))
            if kid:
                kr_analysis_map[kid] = item
    else:
        kr_analysis_map = kr_analysis if isinstance(kr_analysis, dict) else {}

    goal_detail = progress.get("goalDetail", {})
    stats = progress.get("stats", {})

    key_results = []
    for kr_id, kr_info in progress.get("krData", {}).items():
        kr_id_str = str(kr_id)
        kr_a = kr_analysis_map.get(kr_id_str, {})

        actions = []
        for action_id, action_info in progress.get("actionData", {}).items():
            if str(action_info.get("parentKrId", "")) != kr_id_str:
                continue
            action_id_str = str(action_id)
            aj = action_judgments.get(action_id_str, {})

            if action_info.get("excluded"):
                actions.append({
                    "actionId": action_id_str,
                    "fullLevelNumber": action_info.get("fullLevelNumber", ""),
                    "name": action_info.get("name", ""),
                    "excluded": True,
                })
            else:
                r_codes = aj.get("rCodes", [])
                evidence_str = aj.get("evidence", "")
                if not evidence_str and r_codes:
                    evidence_str = ", ".join(r_codes)
                actions.append({
                    "actionId": action_id_str,
                    "fullLevelNumber": action_info.get("fullLevelNumber", ""),
                    "name": action_info.get("name", ""),
                    "excluded": False,
                    "lamp": aj.get("lamp", "black"),
                    "summary": aj.get("summary", ""),
                    "support": aj.get("support", ""),
                    "progress": aj.get("progress", ""),
                    "evidence": evidence_str,
                    "reason": aj.get("reason", ""),
                })

        if kr_info.get("excluded"):
            key_results.append({
                "krId": kr_id_str,
                "fullLevelNumber": kr_info.get("fullLevelNumber", ""),
                "name": kr_info.get("name", ""),
                "measureStandard": kr_info.get("measureStandard", ""),
                "excluded": True,
                "actions": actions,
            })
        else:
            key_results.append({
                "krId": kr_id_str,
                "fullLevelNumber": kr_info.get("fullLevelNumber", ""),
                "name": kr_info.get("name", ""),
                "measureStandard": kr_info.get("measureStandard", ""),
                "excluded": False,
                "monthlyResult": kr_a.get("monthlyResult", ""),
                "gapToStandard": kr_a.get("gapToStandard", ""),
                "momComparison": kr_a.get("momComparison", ""),
                "evidence": kr_a.get("evidence", ""),
                "judgmentReason": kr_a.get("judgmentReason", ""),
                "actions": actions,
            })

    evidence_reports = []
    evidence_stats = {"totalReports": 0, "primaryCount": 0, "secondaryCount": 0}
    for rid, info in evidence_json.get("reports", {}).items():
        evidence_reports.append({
            "reportId": str(rid),
            "rCode": info.get("rCode", ""),
            "title": info.get("title", ""),
            "level": info.get("level", ""),
            "nodes": info.get("nodes", []),
        })
        if info.get("level") == "主证据":
            evidence_stats["primaryCount"] += 1
        else:
            evidence_stats["secondaryCount"] += 1
    evidence_stats["totalReports"] = len(evidence_reports)

    summary = goal_summary if isinstance(goal_summary, dict) else {}

    complete = {
        "$schema": "goal_analysis_v1",
        "goalId": str(args.goal_id),
        "groupId": str(args.group_id),
        "month": args.month,
        "goalInfo": {
            "fullLevelNumber": goal_detail.get("fullLevelNumber", ""),
            "name": goal_detail.get("name", ""),
            "planDateRange": goal_detail.get("planDateRange", ""),
            "statusDesc": goal_detail.get("statusDesc", ""),
            "measureStandard": goal_detail.get("measureStandard", ""),
            "excluded": False,
            "excludeReason": None,
        },
        "lamp": {
            "goalLamp": lamp_json.get("goalLamp", "black"),
            "goalLampEmoji": lamp_json.get("goalLampEmoji", "⚫"),
            "actionCounts": lamp_json.get("actionCounts", {}),
        },
        "commitment": summary.get("commitment", {}),
        "keyResults": key_results,
        "excludedKrCount": stats.get("excludedKrCount", 0),
        "excludedActionCount": stats.get("excludedActionCount", 0),
        "deviations": summary.get("deviations", []),
        "conclusionText": summary.get("conclusionText", ""),
        "goalJudgmentReason": summary.get("goalJudgmentReason", ""),
        "evidence": {
            "reports": evidence_reports,
            "stats": evidence_stats,
        },
    }

    output_path = os.path.join(gd, "goal_complete.json")
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(complete, f, ensure_ascii=False, indent=2)

    _log(f"Done! Goal complete JSON assembled: {output_path} ({len(key_results)} KRs, {len(evidence_reports)} reports)")
    return {"success": True, "outputFile": output_path, "excluded": False}


# ─── validate_goal_json ──────────────────────────────────────────

def validate_goal_json(args):
    """Validate the assembled goal_complete.json against the v1 schema rules.

    Performs 13 validation checks (V1-V13) and returns detailed errors list.
    """
    if not args.goal_id:
        return {"error": "goal_id is required for validate_goal_json"}
    if not args.group_id:
        return {"error": "group_id is required for validate_goal_json"}
    if not args.month:
        return {"error": "month (YYYY-MM) is required for validate_goal_json"}

    gd = _goal_dir(args.group_id, args.month, args.goal_id)
    json_path = os.path.join(gd, "goal_complete.json")
    if not os.path.isfile(json_path):
        return {"error": f"goal_complete.json not found: {json_path}"}

    with open(json_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    errors = []

    # V1: Schema version
    if data.get("$schema") != "goal_analysis_v1":
        errors.append({"code": "V1", "msg": f"$schema must be 'goal_analysis_v1', got '{data.get('$schema')}'"})

    # V2: Required fields
    for field in ["goalId", "groupId", "month", "goalInfo"]:
        if field not in data:
            errors.append({"code": "V2", "msg": f"Missing required field: {field}"})

    goal_info = data.get("goalInfo", {})

    # V3: Excluded goal
    if goal_info.get("excluded"):
        _log("Excluded goal — validation passed (V3)")
        return {"success": True, "valid": True, "errors": [], "skippedReason": "excluded"}

    # V3b: Failed goal
    if data.get("failed"):
        _log("Failed goal — validation passed (V3b)")
        return {"success": True, "valid": True, "errors": [], "skippedReason": "failed"}

    # V4: Lamp consistency
    lamp = data.get("lamp", {})
    if "goalLamp" not in lamp:
        errors.append({"code": "V4", "msg": "lamp.goalLamp is missing"})

    # V5: KR completeness
    kr_required_fields = ["monthlyResult", "gapToStandard", "momComparison", "evidence", "judgmentReason", "measureStandard"]
    for kr in data.get("keyResults", []):
        if kr.get("excluded"):
            continue
        kr_id = kr.get("krId", "?")
        for field in kr_required_fields:
            if field not in kr or kr[field] is None:
                errors.append({"code": "V5", "msg": f"KR {kr_id} missing field: {field}"})

    # V6: Action completeness
    action_required_fields = ["summary", "support", "progress", "evidence", "reason"]
    for kr in data.get("keyResults", []):
        for action in kr.get("actions", []):
            if action.get("excluded"):
                continue
            a_lamp = action.get("lamp", "")
            a_id = action.get("actionId", "?")
            if a_lamp == "black":
                if "lamp" not in action:
                    errors.append({"code": "V6", "msg": f"Black lamp action {a_id} missing 'lamp' field"})
                if "reason" not in action:
                    errors.append({"code": "V6", "msg": f"Black lamp action {a_id} missing 'reason' field"})
            else:
                for field in action_required_fields:
                    if field not in action or action[field] is None:
                        errors.append({"code": "V6", "msg": f"Action {a_id} missing field: {field}"})

    # V7: Action lamp matching (compare with action_judgments.json if exists)
    aj_path = os.path.join(gd, "action_judgments.json")
    if os.path.isfile(aj_path):
        with open(aj_path, "r", encoding="utf-8") as f:
            aj_raw = json.load(f)
        aj_map = {}
        if isinstance(aj_raw, dict) and "actionJudgments" in aj_raw:
            for item in aj_raw["actionJudgments"]:
                aj_map[str(item.get("actionId", ""))] = item
        elif isinstance(aj_raw, list):
            for item in aj_raw:
                aj_map[str(item.get("actionId", ""))] = item
        else:
            aj_map = {str(k): v for k, v in aj_raw.items()} if isinstance(aj_raw, dict) else {}

        bp_path = os.path.join(gd, "black_lamp_prefills.json")
        if os.path.isfile(bp_path):
            with open(bp_path, "r", encoding="utf-8") as f:
                bp_raw = json.load(f)
            for item in bp_raw.get("actionJudgments", []):
                aid = str(item.get("actionId", ""))
                if aid and aid not in aj_map:
                    aj_map[aid] = item

        for kr in data.get("keyResults", []):
            for action in kr.get("actions", []):
                if action.get("excluded"):
                    continue
                a_id = str(action.get("actionId", ""))
                if a_id in aj_map:
                    expected = aj_map[a_id].get("lamp", "")
                    actual = action.get("lamp", "")
                    if expected and actual and expected != actual:
                        errors.append({"code": "V7", "msg": f"Action {a_id} lamp mismatch: JSON={actual}, judgments={expected}"})

    # V8: R-code continuity
    evidence = data.get("evidence", {})
    r_codes = [r.get("rCode", "") for r in evidence.get("reports", []) if r.get("rCode")]
    if r_codes:
        r_code_pattern = re.compile(r'^R(\d+?)(\d{3})$')
        parsed = []
        for rc in r_codes:
            m = r_code_pattern.match(rc)
            if m:
                parsed.append((m.group(1), int(m.group(2))))
        if parsed:
            prefixes = set(p[0] for p in parsed)
            for prefix in prefixes:
                indices = sorted(p[1] for p in parsed if p[0] == prefix)
                expected = list(range(indices[0], indices[0] + len(indices)))
                if indices != expected:
                    errors.append({"code": "V8", "msg": f"R-code discontinuity for prefix R{prefix}: {indices}"})

    # V9: Evidence reference existence
    all_r_codes = set(r_codes)
    ref_pattern = re.compile(r'\b(R\d+)')

    def _check_refs(text, context):
        if not text:
            return
        for m in ref_pattern.finditer(str(text)):
            if m.group(1) not in all_r_codes:
                errors.append({"code": "V9", "msg": f"Referenced {m.group(1)} in {context} not found in evidence"})

    commitment = data.get("commitment", {})
    _check_refs(commitment.get("evidence"), "commitment.evidence")
    for kr in data.get("keyResults", []):
        if not kr.get("excluded"):
            _check_refs(kr.get("evidence"), f"KR {kr.get('krId', '?')}.evidence")
        for action in kr.get("actions", []):
            if not action.get("excluded") and action.get("lamp") != "black":
                _check_refs(action.get("evidence"), f"Action {action.get('actionId', '?')}.evidence")

    # V10: Content non-empty
    if not commitment.get("standard"):
        errors.append({"code": "V10", "msg": "commitment.standard is empty"})
    if not commitment.get("actual"):
        errors.append({"code": "V10", "msg": "commitment.actual is empty"})
    if not data.get("conclusionText"):
        errors.append({"code": "V10", "msg": "conclusionText is empty"})
    if not data.get("goalJudgmentReason"):
        errors.append({"code": "V10", "msg": "goalJudgmentReason is empty"})

    # V11: Deviation format
    for i, dev in enumerate(data.get("deviations", [])):
        for field in ["point", "impact", "hypothesis", "correction"]:
            if field not in dev or not dev[field]:
                errors.append({"code": "V11", "msg": f"deviations[{i}] missing or empty field: {field}"})

    # V12: ID string type
    if not isinstance(data.get("goalId"), str):
        errors.append({"code": "V12", "msg": f"goalId must be string, got {type(data.get('goalId')).__name__}"})
    if not isinstance(data.get("groupId"), str):
        errors.append({"code": "V12", "msg": f"groupId must be string, got {type(data.get('groupId')).__name__}"})
    for kr in data.get("keyResults", []):
        if not isinstance(kr.get("krId"), str):
            errors.append({"code": "V12", "msg": f"krId must be string, got {type(kr.get('krId')).__name__}"})
        for action in kr.get("actions", []):
            if not isinstance(action.get("actionId"), str):
                errors.append({"code": "V12", "msg": f"actionId must be string, got {type(action.get('actionId')).__name__}"})

    valid = len(errors) == 0
    _log(f"Validation {'PASSED' if valid else 'FAILED'}: {len(errors)} error(s)")
    if errors:
        for e in errors:
            _log(f"  [{e['code']}] {e['msg']}")

    return {"success": True, "valid": valid, "errors": errors, "errorCount": len(errors)}


# ─── Action dispatch ──────────────────────────────────────────────

ACTION_MAP = {
    "collect_goal_progress": collect_goal_progress,
    "collect_previous_month_data": collect_previous_month_data,
    "split_prev_report_by_goal": split_prev_report_by_goal,
    "build_goal_evidence": build_goal_evidence,
    "build_judgment_input": build_judgment_input,
    "aggregate_lamp_colors": aggregate_lamp_colors,
    "assemble_goal_json": assemble_goal_json,
    "validate_goal_json": validate_goal_json,
    "save_task_monthly_reading": save_task_monthly_reading,
}


def main():
    parser = argparse.ArgumentParser(
        description="BP Goal Analyzer — single-goal data collection, judgment, and JSON assembly",
    )
    parser.add_argument("action", choices=ACTION_MAP.keys(), help="The action to perform")
    parser.add_argument("--group_id", help="Personal group ID")
    parser.add_argument("--goal_id", help="Goal ID")
    parser.add_argument("--month", help="Target month YYYY-MM")
    parser.add_argument("--output", help="Output file path")
    parser.add_argument("--employee_id", help="Employee ID (for evidence level)")
    parser.add_argument("--report_month", help="Actual report month (for collect_previous_month_data)")
    parser.add_argument("--task_id", help="Task ID (for save_task_monthly_reading)")
    parser.add_argument("--content_file", help="Path to content file")
    parser.add_argument("--content", help="Inline content string")

    args = parser.parse_args()
    result = ACTION_MAP[args.action](args)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    if result.get("error"):
        sys.exit(1)


if __name__ == "__main__":
    main()
