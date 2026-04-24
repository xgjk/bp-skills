#!/usr/bin/env python3
"""Monthly Report API CLI — BP monthly report generation pipeline.

Usage:
    python monthly_report_api.py <action> [options]

Actions:
    init_work_dir               Initialize per-run working directory
    collect_monthly_overview     Fetch task tree + goal list
    collect_goal_progress        Exclusion + progress markdown + black-lamp + reportId extraction
    collect_previous_month_data  Aggregate previous month's reports + evaluations
    build_goal_evidence          Build goal-level evidence ledger with R-code assignment
    build_judgment_input         Assemble judgment material package for each action
    aggregate_lamp_colors        Aggregate action lamp colors -> goal lamp color
    build_evidence_ledger        Merge all goal evidence ledgers into global ledger
    assemble_report              Splice final report from intermediate artifacts
    save_openclaw_report         Save report to BP via saveOpenClawReport (API 2.33)
    save_task_monthly_reading    Save goal monthly reading content (API 2.35)
    update_report_status         Update report generation status (0=generating, 1=success, 2=failed)

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


# ─── Task tree helpers ────────────────────────────────────────────

_SLIM_TASK_FIELDS = ("id", "name", "fullLevelNumber", "type", "reportCycle",
                     "planDateRange", "statusDesc", "periodId", "groupId")


def _slim_task_tree(node):
    """Keep only essential fields in task tree (mirrors bp_api.py logic)."""
    if node is None:
        return None
    if isinstance(node, list):
        return [_slim_task_tree(n) for n in node]
    keep = {k: node[k] for k in _SLIM_TASK_FIELDS if k in node}
    children = node.get("children")
    if children:
        keep["children"] = [_slim_task_tree(c) for c in children]
    return keep


def _collect_all_ids(nodes):
    """Recursively collect all task IDs from a (slim) task tree."""
    ids = []
    for node in (nodes or []):
        nid = node.get("id")
        if nid:
            ids.append(str(nid))
        ids.extend(_collect_all_ids(node.get("children")))
    return ids


def _collect_goal_summary(nodes):
    """Extract summary info for each top-level goal from slim task tree."""
    goals = []
    for node in (nodes or []):
        ntype = node.get("type", "")
        if "目标" in ntype:
            goals.append({
                "goalId": str(node["id"]) if node.get("id") else None,
                "name": _strip_html(node.get("name", "")),
                "fullLevelNumber": node.get("fullLevelNumber", ""),
                "planDateRange": node.get("planDateRange", ""),
                "statusDesc": node.get("statusDesc", ""),
            })
    return goals


def _strip_html(html):
    """Strip HTML tags and convert to plain text. <br> becomes newline."""
    if not html:
        return ""
    text = re.sub(r'<br\s*/?>', '\n', html)
    text = re.sub(r'<[^>]+>', '', text)
    return text.strip()


_ALLOWED_HTML_RE = re.compile(
    r'<(?:span\s+style="color:#[0-9a-fA-F]{6};\s*font-weight:700;">|/span>|div\s+class="people-suggest">|/div>)',
    re.IGNORECASE,
)

_ALL_HTML_RE = re.compile(r'<(?:p|span|div|br|strong|em|ul|ol|li|a|h[1-6])\b', re.IGNORECASE)


def _strip_residual_html(text):
    """Strip unwanted HTML from final report while preserving template-defined tags.

    Keeps: <span style="color:#xxxxxx; font-weight:700;">, </span>,
           <div class="people-suggest">, </div>
    Strips: all other HTML tags (<p>, <strong>, <br>, <a>, etc.)
    """
    if not text:
        return text

    allowed_placeholders = {}
    counter = [0]

    def _save_allowed(m):
        key = f"\x00ALLOWED_{counter[0]}\x00"
        allowed_placeholders[key] = m.group(0)
        counter[0] += 1
        return key

    protected = _ALLOWED_HTML_RE.sub(_save_allowed, text)

    if _ALL_HTML_RE.search(protected):
        _log("Warning: residual HTML detected in final report, stripping...")
        protected = re.sub(r'<br\s*/?>', '\n', protected)
        protected = re.sub(r'<[^>]+>', '', protected)

    for key, original in allowed_placeholders.items():
        protected = protected.replace(key, original)

    return protected


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

def _work_dir(group_id, month):
    """Return the per-run working directory path."""
    return f"/home/node/.openclaw/workspace/files/bp/bp_report_{group_id}_{month}"


def _goal_dir(group_id, month, goal_id):
    """Return the per-goal sub-directory path."""
    return os.path.join(_work_dir(group_id, month), "goals", str(goal_id))


def _parse_plan_date_range(plan_date_range):
    """Parse 'yyyy-MM-dd ~ yyyy-MM-dd' into (start_str, end_str) or (None, None)."""
    if not plan_date_range or "~" not in plan_date_range:
        return None, None
    parts = plan_date_range.split("~")
    start = parts[0].strip() if len(parts) > 0 else None
    end = parts[1].strip() if len(parts) > 1 else None
    return start or None, end or None


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


def _judge_black_lamp(progress_markdown):
    """Check if an action has no valid evidence (black lamp)."""
    if not progress_markdown or not progress_markdown.strip():
        return True
    if progress_markdown.strip() == "# 汇报推进各情况总结":
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

def init_work_dir(args):
    """Initialize the per-run working directory. Cleans up previous run for same group+month."""
    if not args.group_id:
        return {"error": "group_id is required for init_work_dir"}
    if not args.month:
        return {"error": "month (YYYY-MM) is required for init_work_dir"}

    wd = _work_dir(args.group_id, args.month)
    if os.path.exists(wd):
        _log(f"Removing previous work dir: {wd}")
        shutil.rmtree(wd)
    os.makedirs(wd, exist_ok=True)
    os.makedirs(os.path.join(wd, "goals"), exist_ok=True)

    _log(f"Work dir initialized: {wd}")
    return {"success": True, "workDir": wd}


# ─── collect_monthly_overview ─────────────────────────────────────

def collect_monthly_overview(args):
    """Fetch task tree and output goal list + global stats (lightweight).

    This is the first step of the per-goal collection workflow:
    1. Fetch task tree for the group
    2. Extract goal summary list
    3. Write lightweight JSON with tree + goals + stats
    """
    if not args.group_id:
        return {"error": "group_id is required for collect_monthly_overview"}
    if not args.month:
        return {"error": "month (YYYY-MM) is required for collect_monthly_overview"}

    _log("Fetching task tree...")
    tree_result = _request("GET", "/bp/task/v2/getSimpleTree", params={"groupId": args.group_id})
    if not tree_result.get("success"):
        return {"error": f"Failed to fetch task tree: {tree_result.get('error')}"}

    raw_tree = tree_result["data"]
    task_tree = _slim_task_tree(raw_tree) if raw_tree else []
    all_ids = _collect_all_ids(task_tree)
    goals = _collect_goal_summary(task_tree)

    output = {
        "groupId": args.group_id,
        "month": args.month,
        "collectTime": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "taskTree": task_tree,
        "goals": goals,
        "stats": {"totalGoals": len(goals), "totalNodes": len(all_ids)},
    }

    wd = _work_dir(args.group_id, args.month)
    os.makedirs(wd, exist_ok=True)
    output_path = args.output or os.path.join(wd, "overview.json")
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    _log(f"Done! Overview written to {output_path} ({len(goals)} goals, {len(all_ids)} nodes)")
    return {"success": True, "outputFile": output_path, "stats": output["stats"]}


def _backfill_overview(group_id, month, goal_id, goal_detail):
    """Backfill overview.json goals list with fields from getGoalAndKeyResult.

    getSimpleTree does not return fullLevelNumber, planDateRange, or statusDesc
    for goal nodes.  After collect_goal_progress fetches the full detail, this
    function patches the corresponding entry in overview.json so that downstream
    steps (3e, 3f) can read accurate data from a single source.
    """
    wd = _work_dir(group_id, month)
    overview_path = os.path.join(wd, "overview.json")
    if not os.path.isfile(overview_path):
        return

    with open(overview_path, "r", encoding="utf-8") as f:
        overview = json.load(f)

    updated = False
    for g in overview.get("goals", []):
        if str(g.get("goalId", "")) == str(goal_id):
            for field in ("fullLevelNumber", "planDateRange", "statusDesc"):
                new_val = goal_detail.get(field, "")
                if new_val and not g.get(field):
                    g[field] = new_val
                    updated = True
            break

    if updated:
        with open(overview_path, "w", encoding="utf-8") as f:
            json.dump(overview, f, ensure_ascii=False, indent=2)
        _log(f"Backfilled overview.json for goal {goal_id}")


# ─── collect_goal_progress (Phase 2-3) ────────────────────────────

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

    _backfill_overview(args.group_id, args.month, args.goal_id, goal_detail)

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

    r_start = int(getattr(args, "r_start_index", None) or 1)
    employee_id = getattr(args, "employee_id", None) or ""

    gd = _goal_dir(args.group_id, args.month, args.goal_id)
    progress_path = os.path.join(gd, "progress.json")
    if not os.path.isfile(progress_path):
        return {"error": f"progress.json not found: {progress_path}. Run collect_goal_progress first."}

    with open(progress_path, "r", encoding="utf-8") as f:
        progress = json.load(f)

    if progress.get("excluded"):
        md = f"## 目标: {progress['goalDetail'].get('name', '')} 证据台账\n\n> 该目标不参与本月自查，无证据台账。\n"
        output_path = os.path.join(gd, "goal_evidence.md")
        with open(output_path, "w", encoding="utf-8") as f:
            f.write(md)
        return {"success": True, "outputFile": output_path, "nextRIndex": r_start, "rCodeCount": 0}

    seen_report_ids = {}
    month_prefix = args.month[5:7]

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

    r_index = r_start
    r_code_map = {}
    for rid in sorted(seen_report_ids.keys()):
        r_code = f"R{month_prefix}{r_index:02d}"
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

    _log(f"Done! Goal evidence ledger written to {output_path} ({len(seen_report_ids)} reports, R{month_prefix}{r_start:02d}-R{month_prefix}{r_index - 1:02d})")
    return {
        "success": True, "outputFile": output_path, "evidenceJsonFile": evidence_json_path,
        "nextRIndex": r_index, "rCodeCount": len(seen_report_ids),
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
    for action_id, action_info in progress.get("actionData", {}).items():
        if action_info.get("excluded"):
            continue
        if action_info.get("isBlackLamp"):
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

    _log(f"Done! {len(files)} judgment input files written to {gd}")
    return {"success": True, "files": files, "count": len(files)}


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

    for action_id, info in judgments.items():
        if not isinstance(info, dict):
            continue
        lamp = info.get("lamp") or info.get("color") or "green"
        lamp = lamp.lower().strip()
        if lamp not in lamp_priority:
            _log(f"Unknown lamp value '{lamp}' for action {action_id}, defaulting to green")
            lamp = "green"
        counts[lamp] = counts.get(lamp, 0) + 1
        if lamp_priority.get(lamp, 0) > lamp_priority.get(highest, 0):
            highest = lamp

    result = {
        "goalId": args.goal_id,
        "goalLamp": highest,
        "goalLampEmoji": lamp_names.get(highest, ""),
        "counts": counts,
    }

    output_path = os.path.join(gd, "goal_lamp.json")
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    _log(f"Done! Goal lamp: {lamp_names[highest]} ({highest}), counts={counts}")
    return {"success": True, **result, "outputFile": output_path}


# ─── build_evidence_ledger (Phase 8) ─────────────────────────────

def build_evidence_ledger(args):
    """[Phase 8] Merge all goal evidence ledgers into global ledger for appendix.

    Reads each goal's goal_evidence.md/json, merges into a single evidence_ledger.md.
    Also assigns RP codes from previous month data.
    """
    if not args.group_id:
        return {"error": "group_id is required for build_evidence_ledger"}
    if not args.month:
        return {"error": "month (YYYY-MM) is required for build_evidence_ledger"}

    wd = _work_dir(args.group_id, args.month)
    goals_dir = os.path.join(wd, "goals")

    all_reports = {}
    goal_sections = []

    if os.path.isdir(goals_dir):
        for goal_id in sorted(os.listdir(goals_dir)):
            evidence_json_path = os.path.join(goals_dir, goal_id, "goal_evidence.json")
            evidence_md_path = os.path.join(goals_dir, goal_id, "goal_evidence.md")
            if os.path.isfile(evidence_json_path):
                with open(evidence_json_path, "r", encoding="utf-8") as f:
                    ej = json.load(f)
                for rid, info in ej.get("reports", {}).items():
                    if rid not in all_reports:
                        all_reports[rid] = info
            if os.path.isfile(evidence_md_path):
                with open(evidence_md_path, "r", encoding="utf-8") as f:
                    goal_sections.append(f.read())

    prev_month_path = os.path.join(wd, "prev_month.json")
    rp_lines = []
    if os.path.isfile(prev_month_path):
        with open(prev_month_path, "r", encoding="utf-8") as f:
            prev_data = json.load(f)
        for i, item in enumerate(prev_data.get("reports", []), 1):
            rp_code = f"RP{i:02d}"
            rid = item.get("reportRecordId", "")
            title = item.get("title", "")
            type_desc = item.get("reportTypeDesc", "")
            rp_lines.append(
                f"| {rp_code} | {type_desc} | 《{title}》 | [查看汇报](huibao://view?id={rid}) |"
            )

    primary_count = sum(1 for v in all_reports.values() if v.get("level") == "主证据")
    secondary_count = sum(1 for v in all_reports.values() if v.get("level") == "辅证")

    lines = [
        "### 附录：证据索引\n",
        "#### A.1 统计摘要\n",
        f"- 原始工作汇报：{len(all_reports)} 份",
        f"- 经批量通知归并后最终采纳：{len(all_reports)} 份",
        f"- 其中本人主证据：{primary_count} 份、他人关联辅证：{secondary_count} 份\n",
        "#### A.2 证据索引表\n",
        "| R 编号 | 汇报标题 | 证据级别 | 汇报链接 | 关联节点 |",
        "|--------|---------|---------|---------|---------|",
    ]
    for rid in sorted(all_reports.keys()):
        info = all_reports[rid]
        nodes_str = " / ".join(
            f"{n['nodeNumber']} {_strip_html(n['nodeName'])}" for n in info.get("nodes", [])
        )
        lines.append(
            f"| {info.get('rCode', '')} | 《{_strip_html(info.get('title', ''))}》 | {info.get('level', '')} "
            f"| [查看汇报](huibao://view?id={rid}) | {nodes_str} |"
        )

    lines.append("")
    lines.append("#### A.3 上月参考索引\n")
    if rp_lines:
        lines.append("**上月汇报：**\n")
        lines.append("| RP 编号 | 类型 | 标题 | 链接 |")
        lines.append("|---------|------|------|------|")
        lines.extend(rp_lines)

        eval_lines = []
        if os.path.isfile(prev_month_path):
            with open(prev_month_path, "r", encoding="utf-8") as f:
                prev_data_for_eval = json.load(f)
            for ev in prev_data_for_eval.get("evaluations", []):
                eval_md = ev.get("evaluationMarkdown", "")
                if eval_md:
                    eval_lines.append(eval_md)
        if eval_lines:
            lines.append("")
            lines.append("**上月评价摘要：**\n")
            lines.extend(eval_lines)
        else:
            lines.append("")
            lines.append("**上月评价摘要：**\n")
            lines.append("上月无评价记录。")
    else:
        lines.append("首月汇报，无上月参考基线。")

    md_content = "\n".join(lines)
    output_path = os.path.join(wd, "evidence_ledger.md")
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(md_content)

    _log(f"Done! Global evidence ledger written to {output_path} ({len(all_reports)} reports)")
    return {"success": True, "outputFile": output_path, "totalReports": len(all_reports)}


# ─── assemble_report (Phase 15) ──────────────────────────────────

def assemble_report(args):
    """[Phase 15] Splice final report from intermediate artifacts.

    Reads and concatenates: report_header.md, conclusion.md, overview_table.md,
    all goal_report.md files, excluded goals, chapter 3-4 links, evidence_ledger.md.
    """
    if not args.group_id:
        return {"error": "group_id is required for assemble_report"}
    if not args.month:
        return {"error": "month (YYYY-MM) is required for assemble_report"}

    wd = _work_dir(args.group_id, args.month)

    def _read_if_exists(path, fallback=""):
        if os.path.isfile(path):
            with open(path, "r", encoding="utf-8") as f:
                return f.read()
        _log(f"Warning: file not found {path}, using fallback")
        return fallback

    def _strip_leading_heading(text, expected_heading_text):
        """Strip a duplicate heading from the beginning of text if AI included one.

        Matches any markdown heading level (# to ######) whose text matches
        ``expected_heading_text`` (case-insensitive, ignores leading numbering
        like '2.1 ').  Only removes the first line if it matches.
        """
        if not text:
            return text
        lines = text.split("\n", 1)
        first = lines[0].strip()
        cleaned = re.sub(r'^#{1,6}\s+', '', first)
        cleaned = re.sub(r'^\d+(\.\d+)*\s*', '', cleaned).strip()
        expected = re.sub(r'^\d+(\.\d+)*\s*', '', expected_heading_text).strip()
        if cleaned.lower() == expected.lower():
            rest = lines[1] if len(lines) > 1 else ""
            return rest.lstrip("\n")
        return text

    parts = []

    parts.append(_read_if_exists(os.path.join(wd, "report_header.md"), "# BP自查报告\n"))
    parts.append("\n---\n")

    parts.append("### 1. 总体自查结论\n\n")
    conclusion = _read_if_exists(os.path.join(wd, "conclusion.md"), "")
    if conclusion:
        conclusion = _strip_leading_heading(conclusion, "总体自查结论")
        parts.append(conclusion)
        parts.append("\n---\n")

    parts.append("### 2. 目标级自查明细\n")

    overview = _read_if_exists(os.path.join(wd, "overview_table.md"), "")
    if overview:
        overview = _strip_leading_heading(overview, "目标清单总览")
        parts.append("#### 2.1 目标清单总览\n")
        parts.append(overview)
        parts.append("\n")

    parts.append("#### 2.2 目标明细\n")

    goals_dir = os.path.join(wd, "goals")
    goal_count = 0
    if os.path.isdir(goals_dir):
        for goal_id in sorted(os.listdir(goals_dir)):
            report_path = os.path.join(goals_dir, goal_id, "goal_report.md")
            if os.path.isfile(report_path):
                with open(report_path, "r", encoding="utf-8") as f:
                    parts.append(f.read())
                parts.append("\n")
                goal_count += 1

    excluded_path = os.path.join(wd, "excluded_goals.md")
    if os.path.isfile(excluded_path):
        with open(excluded_path, "r", encoding="utf-8") as f:
            excluded_content = f.read()
        excluded_content = _strip_leading_heading(excluded_content, "未参与自查目标说明")
        excluded_content = _strip_leading_heading(excluded_content, "未参与自查目标")
        parts.append(excluded_content)
        parts.append("\n")

    parts.append("\n---\n")

    ch3 = _read_if_exists(os.path.join(wd, "chapter3.md"), "")
    if ch3:
        ch3 = _strip_leading_heading(ch3, "年度结果预判评分")
        parts.append("### 3. 年度结果预判评分\n\n")
        parts.append(ch3)
        parts.append("\n---\n")

    ch4 = _read_if_exists(os.path.join(wd, "chapter4.md"), "")
    if ch4:
        ch4 = _strip_leading_heading(ch4, "月度汇报入口")
        parts.append("### 4. 月度汇报入口\n\n")
        parts.append(ch4)
        parts.append("\n---\n")

    ledger = _read_if_exists(os.path.join(wd, "evidence_ledger.md"), "")
    if ledger:
        parts.append(ledger)

    final_report = "\n".join(parts)

    final_report = _strip_residual_html(final_report)

    output_path = args.output or os.path.join(wd, "report_selfcheck.md")
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(final_report)

    _log(f"Done! Final report assembled: {output_path} ({goal_count} goals, {len(final_report)} chars)")
    return {"success": True, "outputFile": output_path, "goalCount": goal_count, "charCount": len(final_report)}


# ─── save_openclaw_report (Phase 16) ─────────────────────────────

def save_openclaw_report(args):
    """[Phase 16] Save report content to bp_openclaw_task via /bp/monthly/report/save.

    Saves reportContent to bp_openclaw_task and marks task as SUCCESS.
    No reportRecordId needed, no draft sending involved.
    """
    if not args.group_id:
        return {"error": "group_id is required for save_openclaw_report"}
    if not args.month:
        return {"error": "month is required for save_openclaw_report"}
    if not args.content_file:
        return {"error": "content_file is required for save_openclaw_report"}
    if not APP_KEY:
        return {"error": "BP_OPEN_API_APP_KEY is not configured."}

    content_path = args.content_file
    if not os.path.isfile(content_path):
        return {"error": f"Content file not found: {content_path}"}

    with open(content_path, "r", encoding="utf-8") as f:
        content = f.read()

    if not content.strip():
        return {"error": "Content file is empty"}

    body = {
        "groupId": args.group_id,
        "reportContent": content,
        "reportMonth": args.month,
    }

    _log(f"Saving openclaw report: groupId={args.group_id}, month={args.month}")
    result = _request("POST", "/bp/monthly/report/save", json_body=body)

    if result.get("success"):
        _log(f"OpenClaw report saved. groupId={args.group_id}, month={args.month}, taskId={result.get('data')}")

    return result


# ─── save_task_monthly_reading (Step 3d+) ─────────────────────────

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


def update_report_status(args):
    """POST /bp/monthly/report/updateStatus — update monthly report generation status.

    Uses the data-query APP_KEY (not the send-report robot key).
    status: 0=generating, 1=success, 2=failed
    fail_reason: required when status=2
    """
    if not args.group_id:
        return {"error": "group_id is required for update_report_status"}
    if not args.month:
        return {"error": "month (YYYY-MM) is required for update_report_status"}
    if args.status is None:
        return {"error": "status (0/1/2) is required for update_report_status"}

    status_val = int(args.status)
    if status_val not in (0, 1, 2):
        return {"error": "status must be 0 (generating), 1 (success), or 2 (failed)"}
    if status_val == 2 and not args.fail_reason:
        return {"error": "fail_reason is required when status=2 (failed)"}

    body = {
        "groupId": args.group_id,
        "reportMonth": args.month,
        "generateStatus": status_val,
    }
    if args.fail_reason:
        body["failReason"] = args.fail_reason

    _log(f"Updating report status: groupId={args.group_id}, month={args.month}, status={status_val}")
    result = _request("POST", "/bp/monthly/report/updateStatus", json_body=body)

    if result.get("success"):
        _log(f"Report status updated. reportId={result.get('data')}")
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
    # Full text goes to report pool; JSON only keeps preview + charCount
    reports_dir = f"/home/node/.openclaw/workspace/files/bp/reports_{args.group_id}"
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

    report_month = getattr(args, "report_month", None) or getattr(args, "month", "") or ""
    wd = _work_dir(args.group_id, report_month) if report_month else f"/home/node/.openclaw/workspace/files/bp/bp_report_{args.group_id}_prev"
    os.makedirs(wd, exist_ok=True)
    default_path = os.path.join(wd, "prev_month.json")

    output_path = args.output or default_path
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    _log(f"Done! Previous month data written to {output_path}")
    return {"success": True, "outputFile": output_path, "stats": output["stats"]}


ACTION_MAP = {
    "init_work_dir": init_work_dir,
    "collect_monthly_overview": collect_monthly_overview,
    "collect_goal_progress": collect_goal_progress,
    "collect_previous_month_data": collect_previous_month_data,
    "build_goal_evidence": build_goal_evidence,
    "build_judgment_input": build_judgment_input,
    "aggregate_lamp_colors": aggregate_lamp_colors,
    "build_evidence_ledger": build_evidence_ledger,
    "assemble_report": assemble_report,
    "save_openclaw_report": save_openclaw_report,
    "save_task_monthly_reading": save_task_monthly_reading,
    "update_report_status": update_report_status,
}


def main():
    parser = argparse.ArgumentParser(
        description="Monthly Report API — collect data, fetch report content, and send reports",
    )
    parser.add_argument(
        "action",
        choices=ACTION_MAP.keys(),
        help="The action to perform",
    )
    parser.add_argument("--group_id", help="Personal group ID")
    parser.add_argument("--goal_id", help="Goal ID (for collect_goal_progress / build_goal_evidence)")
    parser.add_argument("--month", help="Target month YYYY-MM")
    parser.add_argument("--output", help="Output file path")
    parser.add_argument("--employee_id", help="Employee ID (for evidence level: primary vs secondary)")
    parser.add_argument("--r_start_index", help="R-code start index (for build_goal_evidence, default=1)")
    parser.add_argument("--report_month", help="The actual report month (for collect_previous_month_data to locate work dir)")
    parser.add_argument("--task_id", help="Task ID (for save_task_monthly_reading)")
    parser.add_argument("--content_file", help="Path to markdown/html content file")
    parser.add_argument("--content", help="Inline content string (for save_task_monthly_reading, alternative to --content_file)")
    parser.add_argument("--status", help="Generate status: 0=generating, 1=success, 2=failed (for update_report_status)")
    parser.add_argument("--fail_reason", help="Failure reason (for update_report_status, required when status=2)")

    args = parser.parse_args()

    result = ACTION_MAP[args.action](args)

    print(json.dumps(result, ensure_ascii=False, indent=2))

    if result.get("error"):
        sys.exit(1)


if __name__ == "__main__":
    main()
