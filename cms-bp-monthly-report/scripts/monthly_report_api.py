#!/usr/bin/env python3
"""Monthly Report API CLI — BP monthly report generation pipeline.

Usage:
    python monthly_report_api.py <action> [options]

Actions (Skill A — per-goal):
    init_work_dir               Initialize per-run working directory
    collect_goal_progress        Exclusion + progress markdown + black-lamp + reportId extraction
    collect_previous_month_data  Aggregate previous month's reports + evaluations
    split_prev_report_by_goal   Split prev report into per-goal sections for MoM comparison
    build_goal_evidence          Build goal-level evidence ledger with R-code (R{goalSeq}{NNN})
    build_judgment_input         Assemble judgment material package + pre-fill black lamp
    aggregate_lamp_colors        Aggregate action lamp colors -> goal lamp color
    assemble_goal_json           Assemble complete goal JSON from AI fragments + script data
    validate_goal_json           Validate goal_complete.json against v1 schema (13 checks)

Actions (Skill B — global assembly):
    collect_monthly_overview     Fetch task tree + goal list
    fetch_goal_readings          Fetch all goal JSONs from remote API (A10)
    render_full_report           One-shot render entire report from goal JSONs + AI conclusion

Actions (shared):
    build_evidence_ledger        Merge all goal evidence ledgers into global ledger (legacy)
    render_goal_report           Render goal_report.md from goal_report_data.json (legacy)
    render_conclusion            Render conclusion.md from conclusion_data.json (legacy)
    render_overview_table        Render overview_table.md from overview_data.json (legacy)
    render_report_header         Render report_header.md from header_data.json (legacy)
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
    return f"/Users/openclaw-data/bp/bp_report_{group_id}_{month}"


def _goal_dir(group_id, month, goal_id):
    """Return the per-goal working directory path.

    In standalone mode (Skill A), each goal has its own top-level directory:
      /Users/openclaw-data/bp/{groupId}_{goalId}_{month}/
    In aggregate mode (Skill B), goals are nested under the report directory:
      /Users/openclaw-data/bp/bp_report_{groupId}_{month}/goals/{goalId}/
    """
    standalone = os.environ.get("BP_GOAL_STANDALONE")
    if standalone and standalone.lower() in ("1", "true", "yes"):
        return f"/Users/openclaw-data/bp/{group_id}_{goal_id}_{month}"
    return os.path.join(_work_dir(group_id, month), "goals", str(goal_id))


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
    "暂无汇报",
    "无推进记录",
    "暂无推进记录",
    "无汇报内容",
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
    standalone = os.environ.get("BP_GOAL_STANDALONE", "").lower() in ("1", "true", "yes")
    if standalone:
        if os.path.isdir(gd):
            import shutil
            for item in os.listdir(gd):
                item_path = os.path.join(gd, item)
                if os.path.isfile(item_path):
                    os.remove(item_path)
                elif os.path.isdir(item_path):
                    shutil.rmtree(item_path)
            _log(f"Standalone mode: cleared existing directory {gd}")
    os.makedirs(gd, exist_ok=True)
    output_path = args.output or os.path.join(gd, "progress.json")
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    if not standalone:
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


# ─── Lamp rendering constants ─────────────────────────────────────

LAMP_COLOR_MAP = {
    "green": {"emoji": "🟢", "css": "#2e7d32"},
    "yellow": {"emoji": "🟡", "css": "#b26a00"},
    "red": {"emoji": "🔴", "css": "#c62828"},
    "black": {"emoji": "⚫", "css": "#212121"},
}

_PEOPLE_SUGGEST_TEMPLATE = (
    '<div class="people-suggest">\n'
    '  <span style="color:{css}; font-weight:700;">人工判断：待确认（请填写：同意 / 不同意）</span>\n'
    '  <span style="color:{css}; font-weight:700;">若同意：请明确填写"同意"。</span>\n'
    '  <span style="color:{css}; font-weight:700;">若不同意：请填写理由类别（BP不清晰 / 举证材料不足 / AI判断错误 / 其他）及具体说明。</span>\n'
    '  <span style="color:{css}; font-weight:700;">整改方案：待补充</span>\n'
    '  <span style="color:{css}; font-weight:700;">承诺完成时间：待补充</span>\n'
    '  <span style="color:{css}; font-weight:700;">下周期具体举措：待补充</span>\n'
    '</div>'
)


def _render_lamp_block(lamp_color, reason):
    """Render a traffic-light judgment block for the given lamp color and reason text."""
    info = LAMP_COLOR_MAP.get(lamp_color, LAMP_COLOR_MAP["green"])
    css = info["css"]
    emoji = info["emoji"]
    lines = [f'- <span style="color:{css}; font-weight:700;">四灯判断：{emoji}</span>']
    if lamp_color == "green":
        lines.append(f'  <span style="color:{css}; font-weight:700;">判断理由：{reason}</span>')
    else:
        lines.append(f'<span style="color:{css}; font-weight:700;">判断理由：{reason}</span>')
        lines.append(_PEOPLE_SUGGEST_TEMPLATE.format(css=css))
    return "\n".join(lines)


def _render_conclusion_sentence(lamp_color, text):
    """Render the one-line conclusion sentence with correct lamp emoji and color."""
    info = LAMP_COLOR_MAP.get(lamp_color, LAMP_COLOR_MAP["green"])
    return (f'结论一句话：<span style="color:{info["css"]}; font-weight:700;">'
            f'{info["emoji"]} {_lamp_label(lamp_color)}</span>：{text}')


def _lamp_label(lamp_color):
    labels = {"green": "绿灯", "yellow": "黄灯", "red": "红灯", "black": "黑灯"}
    return labels.get(lamp_color, "绿灯")


# ─── render_goal_report (Phase 10) ───────────────────────────────

def render_goal_report(args):
    """[Phase 10] Render goal_report.md from goal_report_data.json + goal_lamp.json.

    AI produces structured JSON (content only), this function renders the
    fixed-template Markdown with correct formatting, lamp blocks, and HTML.
    """
    if not args.goal_id:
        return {"error": "goal_id is required for render_goal_report"}
    if not args.group_id:
        return {"error": "group_id is required for render_goal_report"}
    if not args.month:
        return {"error": "month (YYYY-MM) is required for render_goal_report"}

    gd = _goal_dir(args.group_id, args.month, args.goal_id)
    data_path = os.path.join(gd, "goal_report_data.json")
    lamp_path = os.path.join(gd, "goal_lamp.json")

    if not os.path.isfile(data_path):
        return {"error": f"goal_report_data.json not found: {data_path}"}
    if not os.path.isfile(lamp_path):
        return {"error": f"goal_lamp.json not found: {lamp_path}"}

    with open(data_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    with open(lamp_path, "r", encoding="utf-8") as f:
        lamp = json.load(f)

    goal_lamp = lamp.get("goalLamp", "green")
    goal_number = data.get("fullLevelNumber", "")
    goal_name = data.get("goalName", "")

    lines = [f"##### {goal_number}｜{goal_name}", ""]

    # Section 1: 承诺与实际对照
    lines.append("**承诺与实际对照**")
    lines.append("")
    c = data.get("commitment", {})
    lines.append(f'承诺口径：{c.get("standard", "")}  ')
    lines.append(f'本月实际：{c.get("actual", "")}  ')
    lines.append(f'差异点（若有）：{c.get("gap", "无")}  ')
    evidence_str = c.get("evidence", "")
    lines.append(f'证据：{evidence_str}')
    lines.append("")

    # Section 2: 关键成果达成与举措推进
    lines.append("**关键成果达成与举措推进**")
    lines.append("")

    for kr in data.get("keyResults", []):
        kr_number = kr.get("fullLevelNumber", "")
        kr_name = kr.get("name", "")
        lines.append(f"**关键成果 {kr_number}：{kr_name}**")
        lines.append("")
        lines.append(f'- **衡量标准：** {kr.get("measureStandard", "")}')
        lines.append(f'- **本月结果：** {kr.get("monthlyResult", "")}')
        lines.append(f'- **距离衡量标准：** {kr.get("gapToStandard", "")}')
        lines.append(f'- **环比上月：** {kr.get("momComparison", "")}')
        lines.append(f'- **证据：** {kr.get("evidence", "")}')
        lines.append(f'- **判断理由：** {kr.get("judgmentReason", "")}')
        lines.append("")

        for action in kr.get("actions", []):
            if action.get("excluded"):
                continue
            a_number = action.get("fullLevelNumber", "")
            a_name = action.get("name", "")
            a_lamp = action.get("lamp", "green")
            lines.append(f"- **└ 支撑举措 {a_number}：{a_name}**")
            lines.append(f'  - 推进动作摘要：{action.get("summary", "")}')
            lines.append(f'  - 对结果支撑：【{action.get("support", "中")}】')
            lines.append(f'  - 当前进度：{action.get("progress", "")}')
            lines.append(f'  - 证据：{action.get("evidence", "")}')
            lines.append(_render_lamp_block(a_lamp, action.get('reason', '')))
            lines.append("")

        excluded_actions = [a for a in kr.get("actions", []) if a.get("excluded")]
        if excluded_actions:
            lines.append(f"> 另有 {len(excluded_actions)} 个举措计划期未覆盖本月，不纳入自查。")
            lines.append("")

    excluded_krs = data.get("excludedKrCount", 0)
    excluded_action_total = data.get("excludedActionCount", 0)
    if excluded_krs or excluded_action_total:
        parts = []
        if excluded_krs:
            parts.append(f"{excluded_krs} 个关键成果")
        if excluded_action_total:
            parts.append(f"{excluded_action_total} 个举措")
        lines.append(f'> 另有 {"、".join(parts)}计划期未覆盖本月，不纳入自查。')
        lines.append("")

    # Section 3: 偏差问题与原因分析
    lines.append("**偏差问题与原因分析**")
    lines.append("")
    deviations = data.get("deviations", [])
    if not deviations:
        lines.append("本目标本期无重大偏差。")
    else:
        for dev in deviations:
            lines.append(f'偏差点：{dev.get("point", "")}  ')
            lines.append(f'影响：{dev.get("impact", "")}  ')
            lines.append(f'原因假设：{dev.get("hypothesis", "")}  ')
            lines.append(f'下月纠偏方向：{dev.get("correction", "")}  ')
            if dev.get("evidence"):
                lines.append(f'证据：{dev.get("evidence")}')
            lines.append("")
    lines.append("")

    # Section 4: 目标级综合灯色结论
    lines.append("**目标级综合灯色结论**")
    lines.append("")
    conclusion_text = data.get("conclusionText", "")
    lines.append(_render_conclusion_sentence(goal_lamp, conclusion_text))
    lines.append("")
    goal_reason = data.get("goalJudgmentReason", "")
    lines.append(_render_lamp_block(goal_lamp, goal_reason))
    lines.append("")

    md_content = "\n".join(lines)
    output_path = os.path.join(gd, "goal_report.md")
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(md_content)

    _log(f"Done! Goal report rendered: {output_path} ({len(md_content)} chars)")
    return {"success": True, "outputFile": output_path}


# ─── render_conclusion (Phase 13) ────────────────────────────────

def render_conclusion(args):
    """[Phase 13] Render conclusion.md from conclusion_data.json + all goal_lamp.json files.

    AI produces JSON with summary texts; this function renders the fixed-template
    conclusion Markdown with accurate lamp statistics computed from goal_lamp.json files.
    """
    if not args.group_id:
        return {"error": "group_id is required for render_conclusion"}
    if not args.month:
        return {"error": "month (YYYY-MM) is required for render_conclusion"}

    wd = _work_dir(args.group_id, args.month)
    data_path = os.path.join(wd, "conclusion_data.json")
    if not os.path.isfile(data_path):
        return {"error": f"conclusion_data.json not found: {data_path}"}

    with open(data_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    overview_path = os.path.join(wd, "overview.json")
    if not os.path.isfile(overview_path):
        return {"error": f"overview.json not found: {overview_path}"}
    with open(overview_path, "r", encoding="utf-8") as f:
        overview = json.load(f)

    goals_dir = os.path.join(wd, "goals")
    lamp_counts = {"green": 0, "yellow": 0, "red": 0, "black": 0}
    participating = 0
    excluded_count = 0

    for goal in overview.get("goals", []):
        gid = str(goal.get("goalId", ""))
        progress_path = os.path.join(goals_dir, gid, "progress.json")
        if os.path.isfile(progress_path):
            with open(progress_path, "r", encoding="utf-8") as f:
                prog = json.load(f)
            if prog.get("excluded"):
                excluded_count += 1
                continue

        lamp_file = os.path.join(goals_dir, gid, "goal_lamp.json")
        if os.path.isfile(lamp_file):
            with open(lamp_file, "r", encoding="utf-8") as f:
                gl = json.load(f)
            color = gl.get("goalLamp", "green")
            lamp_counts[color] = lamp_counts.get(color, 0) + 1
            participating += 1
        else:
            excluded_count += 1

    lines = [
        "#### 1.1 结论",
        "",
        f'一句话优势：{data.get("strength", "")}  ',
        f'一句话短板：{data.get("weakness", "")}',
        "",
        "#### 1.2 灯色分布概览",
        "",
        "```text",
        f"参与自查目标 {participating} 个：",
        f"  🟢 目标数：{lamp_counts['green']}",
        f"  🟡 目标数：{lamp_counts['yellow']}",
        f"  🔴 目标数：{lamp_counts['red']}",
        f"  ⚫ 目标数：{lamp_counts['black']}",
        "未参与自查：",
        f"  ★ 未启动：{excluded_count} 个目标",
        "```",
        "",
        "#### 1.3 本月最关键偏差点",
        "",
    ]

    deviations = data.get("topDeviations", [])
    if not deviations:
        lines.append("本月无重大偏差点。")
    else:
        for i, dev in enumerate(deviations, 1):
            lines.append(f'{i}) 偏差点：{dev.get("point", "")}（对应目标：{dev.get("goalNumber", "")}）  ')
            lines.append(f'影响：{dev.get("impact", "")}  ')
            lines.append(f'原因假设：{dev.get("hypothesis", "")}  ')
            lines.append(f'下月纠偏方向：{dev.get("correction", "")}')
            lines.append("")

    md_content = "\n".join(lines)
    output_path = os.path.join(wd, "conclusion.md")
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(md_content)

    _log(f"Done! Conclusion rendered: {output_path}")
    return {"success": True, "outputFile": output_path,
            "lampCounts": lamp_counts, "participating": participating, "excluded": excluded_count}


# ─── render_overview_table (Phase 12) ────────────────────────────

def render_overview_table(args):
    """[Phase 12] Render overview_table.md from overview_data.json + goal_lamp.json files.

    AI produces JSON with per-goal summary texts; this function renders
    the 7-column overview table with correct lamp emojis from goal_lamp.json.
    """
    if not args.group_id:
        return {"error": "group_id is required for render_overview_table"}
    if not args.month:
        return {"error": "month (YYYY-MM) is required for render_overview_table"}

    wd = _work_dir(args.group_id, args.month)
    data_path = os.path.join(wd, "overview_data.json")
    if not os.path.isfile(data_path):
        return {"error": f"overview_data.json not found: {data_path}"}

    with open(data_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    goals_dir = os.path.join(wd, "goals")

    lines = [
        "| 目标编号 | BP目标 | 本月承诺口径 | 本月实际 | 证据引用 | 目标灯色 | 结论一句话 |",
        "|---------|--------|-------------|---------|----------|----------|------------|",
    ]

    for goal in data.get("goals", []):
        gid = str(goal.get("goalId", ""))
        number = goal.get("fullLevelNumber", "")
        name = goal.get("name", "")
        is_excluded = goal.get("excluded", False)

        if is_excluded:
            reason = goal.get("excludeReason", "")
            lines.append(
                f'| {number} | {name} | — | — | '
                f'| <span style="color:#2e7d32; font-weight:700;">★</span> '
                f'| 未启动（{reason}） |'
            )
        else:
            lamp_file = os.path.join(goals_dir, gid, "goal_lamp.json")
            lamp_color = "green"
            if os.path.isfile(lamp_file):
                with open(lamp_file, "r", encoding="utf-8") as f:
                    gl = json.load(f)
                lamp_color = gl.get("goalLamp", "green")
            info = LAMP_COLOR_MAP.get(lamp_color, LAMP_COLOR_MAP["green"])
            lamp_span = f'<span style="color:{info["css"]}; font-weight:700;">{info["emoji"]}</span>'

            lines.append(
                f'| {number} | {name} '
                f'| {goal.get("standard", "—")} '
                f'| {goal.get("actual", "—")} '
                f'| {goal.get("evidence", "")} '
                f'| {lamp_span} '
                f'| {goal.get("conclusion", "")} |'
            )

    md_content = "\n".join(lines)
    output_path = os.path.join(wd, "overview_table.md")
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(md_content)

    _log(f"Done! Overview table rendered: {output_path}")
    return {"success": True, "outputFile": output_path}


# ─── render_report_header ────────────────────────────────────────

def render_report_header(args):
    """Render report_header.md from header_data.json.

    Produces the exact header format: title line + blockquote metadata.
    """
    if not args.group_id:
        return {"error": "group_id is required for render_report_header"}
    if not args.month:
        return {"error": "month (YYYY-MM) is required for render_report_header"}

    wd = _work_dir(args.group_id, args.month)
    data_path = os.path.join(wd, "header_data.json")
    if not os.path.isfile(data_path):
        return {"error": f"header_data.json not found: {data_path}"}

    with open(data_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    employee_name = data.get("employeeName", "")
    year = int(args.month[:4])
    month = int(args.month[5:7])
    period_name = data.get("periodName", "")
    baseline = data.get("baseline", "首月，无基线")

    lines = [
        f"# {employee_name} {year}年{month}月 BP自查报告",
        "",
        f"> 周期：`{period_name}`",
        f"> 节点：`{employee_name}`",
        f"> 基线：{baseline}",
        "> 证据说明：本报告中 R 编号（如 R0101）为当月证据引用，RP 编号（如 RP01）为上月参考引用，点击均可直接查看对应汇报详情。",
        "> 解释口径：灯色按目标级综合判断。",
    ]

    md_content = "\n".join(lines)
    output_path = os.path.join(wd, "report_header.md")
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(md_content)

    _log(f"Done! Report header rendered: {output_path}")
    return {"success": True, "outputFile": output_path}


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
        if not text:
            return text
        lines = text.split("\n")
        expected = re.sub(r'^\d+(\.\d+)*\.?\s*', '', expected_heading_text).strip().lower()
        cleaned_lines = []
        scanned = 0
        for line in lines:
            if scanned >= 5:
                cleaned_lines.append(line)
                continue
            stripped = line.strip()
            if not stripped:
                if scanned == 0:
                    continue
                cleaned_lines.append(line)
                continue
            scanned += 1
            heading_match = re.match(r'^#{1,6}\s+(.*)', stripped)
            if heading_match:
                heading_text = heading_match.group(1)
                normalized = re.sub(r'^\d+(\.\d+)*\.?\s*', '', heading_text).strip().lower()
                if normalized == expected:
                    continue
            cleaned_lines.append(line)
        return "\n".join(cleaned_lines).lstrip("\n")

    parts = []

    header = _read_if_exists(os.path.join(wd, "report_header.md"), "# BP自查报告\n")
    parts.append(header)
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
        overview = _strip_leading_heading(overview, "目标级自查明细")
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
    # Full text goes to prev_reports/ subdir inside current month work dir; JSON only keeps preview + charCount
    report_month = getattr(args, "report_month", None) or getattr(args, "month", "") or ""
    standalone = os.environ.get("BP_GOAL_STANDALONE", "").lower() in ("1", "true", "yes")
    goal_id = getattr(args, "goal_id", None)
    if standalone and goal_id and report_month:
        wd = _goal_dir(args.group_id, report_month, goal_id)
    elif report_month:
        wd = _work_dir(args.group_id, report_month)
    else:
        wd = f"/Users/openclaw-data/bp/bp_report_{args.group_id}_prev"
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
    standalone = os.environ.get("BP_GOAL_STANDALONE", "").lower() in ("1", "true", "yes")
    wd = gd if standalone else _work_dir(args.group_id, args.month)

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
        rf'^(#{3,6}\s+{escaped_number}[｜|])',
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
    next_heading = re.compile(r'^#{3,5}\s+(?:P\d+|###?\s+\d)', re.MULTILINE)
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


# ─── fetch_goal_readings ─────────────────────────────────────────

def fetch_goal_readings(args):
    """Fetch all goal-level JSONs from remote via monthlyReading/query API (A10).

    Reads goal IDs from overview.json, fetches each goal's saved content,
    parses JSON, and writes to local goals/{goalId}/goal_complete.json.
    """
    if not args.group_id:
        return {"error": "group_id is required for fetch_goal_readings"}
    if not args.month:
        return {"error": "month (YYYY-MM) is required for fetch_goal_readings"}

    wd = _work_dir(args.group_id, args.month)
    overview_path = os.path.join(wd, "overview.json")
    if not os.path.isfile(overview_path):
        return {"error": f"overview.json not found: {overview_path}. Run init_work_dir / collect_monthly_overview first."}

    with open(overview_path, "r", encoding="utf-8") as f:
        overview = json.load(f)

    goal_ids = []
    for goal in overview.get("goals", []):
        gid = str(goal.get("goalId", ""))
        if gid:
            goal_ids.append(gid)

    if not goal_ids:
        return {"error": "No goal IDs found in overview.json"}

    goals_dir = os.path.join(wd, "goals")
    os.makedirs(goals_dir, exist_ok=True)

    results = {"fetched": [], "failed": [], "parsed": 0, "errors": []}

    for gid in goal_ids:
        _log(f"Fetching reading for goal {gid}...")
        resp = _request("GET", "/bp/task/monthlyReading/get",
                         params={"taskId": gid, "month": args.month})

        if not resp.get("success"):
            _log(f"  Failed to fetch goal {gid}: {resp.get('error')}")
            results["failed"].append(gid)
            results["errors"].append({"goalId": gid, "error": resp.get("error")})

            gd = os.path.join(goals_dir, gid)
            os.makedirs(gd, exist_ok=True)
            failed_json = {
                "$schema": "goal_analysis_v1",
                "goalId": gid,
                "groupId": str(args.group_id),
                "month": args.month,
                "goalInfo": {"fullLevelNumber": "", "name": "", "excluded": False},
                "failed": True,
                "failReason": f"远端读取失败: {resp.get('error', 'unknown')}",
            }
            with open(os.path.join(gd, "goal_complete.json"), "w", encoding="utf-8") as f:
                json.dump(failed_json, f, ensure_ascii=False, indent=2)
            continue

        resp_data = resp.get("data")
        if not resp_data:
            _log(f"  Goal {gid} returned null data (no record for this month)")
            results["failed"].append(gid)
            results["errors"].append({"goalId": gid, "error": "该月份无记录 (data=null)"})
            continue

        content = resp_data.get("content") if isinstance(resp_data, dict) else resp_data
        if not content:
            _log(f"  Goal {gid} returned empty content")
            results["failed"].append(gid)
            results["errors"].append({"goalId": gid, "error": "content 为空"})
            continue

        content_str = content if isinstance(content, str) else str(content)

        try:
            goal_json = json.loads(content_str)
        except json.JSONDecodeError as e:
            _log(f"  Goal {gid} content is not valid JSON: {e}")
            results["failed"].append(gid)
            results["errors"].append({"goalId": gid, "error": f"JSON parse error: {e}"})
            continue

        gd = os.path.join(goals_dir, gid)
        os.makedirs(gd, exist_ok=True)
        output_path = os.path.join(gd, "goal_complete.json")
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(goal_json, f, ensure_ascii=False, indent=2)

        results["fetched"].append(gid)
        results["parsed"] += 1
        _log(f"  Goal {gid} fetched and saved ({len(content_str)} chars)")

    _log(f"Done! Fetched {results['parsed']}/{len(goal_ids)} goals, {len(results['failed'])} failed")
    return {"success": True, **results, "totalGoals": len(goal_ids)}


# ─── render_full_report ──────────────────────────────────────────

def render_full_report(args):
    """One-shot render of the complete report from goal_complete.json files.

    For Skill B: reads all goal_complete.json (from fetch_goal_readings),
    conclusion_data.json (from AI), and prev_month.json (for A.3),
    then renders all Markdown components and assembles the final report.
    """
    if not args.group_id:
        return {"error": "group_id is required for render_full_report"}
    if not args.month:
        return {"error": "month (YYYY-MM) is required for render_full_report"}

    wd = _work_dir(args.group_id, args.month)
    goals_dir = os.path.join(wd, "goals")

    goal_jsons = []
    if os.path.isdir(goals_dir):
        for goal_id in sorted(os.listdir(goals_dir)):
            gc_path = os.path.join(goals_dir, goal_id, "goal_complete.json")
            if os.path.isfile(gc_path):
                with open(gc_path, "r", encoding="utf-8") as f:
                    goal_jsons.append(json.load(f))

    if not goal_jsons:
        return {"error": "No goal_complete.json files found. Run fetch_goal_readings first."}

    participating = [g for g in goal_jsons if not g.get("goalInfo", {}).get("excluded") and not g.get("failed")]
    excluded = [g for g in goal_jsons if g.get("goalInfo", {}).get("excluded")]
    failed = [g for g in goal_jsons if g.get("failed")]

    lamp_counts = {"green": 0, "yellow": 0, "red": 0, "black": 0}
    for g in participating:
        color = g.get("lamp", {}).get("goalLamp", "black")
        lamp_counts[color] = lamp_counts.get(color, 0) + 1

    # --- Render overview_table.md ---
    ot_lines = [
        "| 目标编号 | BP目标 | 本月承诺口径 | 本月实际 | 证据引用 | 目标灯色 | 结论一句话 |",
        "|---------|--------|-------------|---------|----------|----------|------------|",
    ]
    for g in goal_jsons:
        gi = g.get("goalInfo", {})
        number = gi.get("fullLevelNumber", "")
        name = gi.get("name", "")

        if g.get("failed"):
            ot_lines.append(
                f'| {number} | {name} | — | — | — '
                f'| <span style="color:red; font-weight:700;">❌</span> '
                f'| 数据生成失败 |'
            )
        elif gi.get("excluded"):
            reason = gi.get("excludeReason", "")
            ot_lines.append(
                f'| {number} | {name} | — | — | — '
                f'| <span style="color:#2e7d32; font-weight:700;">★</span> '
                f'| 未启动（{reason}） |'
            )
        else:
            lamp_color = g.get("lamp", {}).get("goalLamp", "black")
            info = LAMP_COLOR_MAP.get(lamp_color, LAMP_COLOR_MAP["green"])
            lamp_span = f'<span style="color:{info["css"]}; font-weight:700;">{info["emoji"]}</span>'
            c = g.get("commitment", {})
            ot_lines.append(
                f'| {number} | {name} '
                f'| {c.get("standard", "—")} '
                f'| {c.get("actual", "—")} '
                f'| {c.get("evidence", "")} '
                f'| {lamp_span} '
                f'| {g.get("conclusionText", "")} |'
            )

    with open(os.path.join(wd, "overview_table.md"), "w", encoding="utf-8") as f:
        f.write("\n".join(ot_lines))

    # --- Render conclusion.md ---
    conclusion_path = os.path.join(wd, "conclusion_data.json")
    if os.path.isfile(conclusion_path):
        with open(conclusion_path, "r", encoding="utf-8") as f:
            conclusion_data = json.load(f)
    else:
        conclusion_data = {}

    cl_lines = [
        "#### 1.1 结论", "",
        f'一句话优势：{conclusion_data.get("strength", "本月无参与自查的目标")}  ',
        f'一句话短板：{conclusion_data.get("weakness", "")}', "",
        "#### 1.2 灯色分布概览", "",
        "```text",
        f"参与自查目标 {len(participating)} 个：",
        f"  🟢 目标数：{lamp_counts['green']}",
        f"  🟡 目标数：{lamp_counts['yellow']}",
        f"  🔴 目标数：{lamp_counts['red']}",
        f"  ⚫ 目标数：{lamp_counts['black']}",
        "未参与自查：",
        f"  ★ 未启动：{len(excluded)} 个目标",
    ]
    if failed:
        cl_lines.append(f"  ❌ 数据失败：{len(failed)} 个目标")
    cl_lines.extend(["```", "", "#### 1.3 本月最关键偏差点", ""])

    deviations = conclusion_data.get("topDeviations", [])
    if not deviations:
        cl_lines.append("本月无重大偏差点。")
    else:
        for i, dev in enumerate(deviations, 1):
            cl_lines.append(f'{i}) 偏差点：{dev.get("point", "")}（对应目标：{dev.get("goalNumber", "")}）  ')
            cl_lines.append(f'影响：{dev.get("impact", "")}  ')
            cl_lines.append(f'原因假设：{dev.get("hypothesis", "")}  ')
            cl_lines.append(f'下月纠偏方向：{dev.get("correction", "")}')
            cl_lines.append("")

    with open(os.path.join(wd, "conclusion.md"), "w", encoding="utf-8") as f:
        f.write("\n".join(cl_lines))

    # --- Render each goal_report.md from JSON ---
    for g in participating:
        gid = str(g.get("goalId", ""))
        gi = g.get("goalInfo", {})
        lamp_color = g.get("lamp", {}).get("goalLamp", "green")
        number = gi.get("fullLevelNumber", "")
        name = gi.get("name", "")

        lines = [f"##### {number}｜{name}", ""]

        lines.append("**承诺与实际对照**")
        lines.append("")
        c = g.get("commitment", {})
        lines.append(f'承诺口径：{c.get("standard", "")}  ')
        lines.append(f'本月实际：{c.get("actual", "")}  ')
        lines.append(f'差异点（若有）：{c.get("gap", "无")}  ')
        lines.append(f'证据：{c.get("evidence", "")}')
        lines.append("")

        lines.append("**关键成果达成与举措推进**")
        lines.append("")

        for kr in g.get("keyResults", []):
            if kr.get("excluded"):
                continue
            lines.append(f'**关键成果 {kr.get("fullLevelNumber", "")}：{kr.get("name", "")}**')
            lines.append("")
            lines.append(f'- **衡量标准：** {kr.get("measureStandard", "")}')
            lines.append(f'- **本月结果：** {kr.get("monthlyResult", "")}')
            lines.append(f'- **距离衡量标准：** {kr.get("gapToStandard", "")}')
            lines.append(f'- **环比上月：** {kr.get("momComparison", "")}')
            lines.append(f'- **证据：** {kr.get("evidence", "")}')
            lines.append(f'- **判断理由：** {kr.get("judgmentReason", "")}')
            lines.append("")

            for action in kr.get("actions", []):
                if action.get("excluded"):
                    continue
                a_lamp = action.get("lamp", "green")
                lines.append(f'- **└ 支撑举措 {action.get("fullLevelNumber", "")}：{action.get("name", "")}**')
                lines.append(f'  - 推进动作摘要：{action.get("summary", "")}')
                lines.append(f'  - 对结果支撑：【{action.get("support", "中")}】')
                lines.append(f'  - 当前进度：{action.get("progress", "")}')
                lines.append(f'  - 证据：{action.get("evidence", "")}')
                lines.append(_render_lamp_block(a_lamp, action.get("reason", "")))
                lines.append("")

            excluded_actions = [a for a in kr.get("actions", []) if a.get("excluded")]
            if excluded_actions:
                lines.append(f"> 另有 {len(excluded_actions)} 个举措计划期未覆盖本月，不纳入自查。")
                lines.append("")

        excluded_krs = g.get("excludedKrCount", 0)
        excluded_acts = g.get("excludedActionCount", 0)
        if excluded_krs or excluded_acts:
            parts = []
            if excluded_krs:
                parts.append(f"{excluded_krs} 个关键成果")
            if excluded_acts:
                parts.append(f"{excluded_acts} 个举措")
            lines.append(f'> 另有 {"、".join(parts)}计划期未覆盖本月，不纳入自查。')
            lines.append("")

        lines.append("**偏差问题与原因分析**")
        lines.append("")
        devs = g.get("deviations", [])
        if not devs:
            lines.append("本目标本期无重大偏差。")
        else:
            for dev in devs:
                lines.append(f'偏差点：{dev.get("point", "")}  ')
                lines.append(f'影响：{dev.get("impact", "")}  ')
                lines.append(f'原因假设：{dev.get("hypothesis", "")}  ')
                lines.append(f'下月纠偏方向：{dev.get("correction", "")}  ')
                if dev.get("evidence"):
                    lines.append(f'证据：{dev.get("evidence")}')
                lines.append("")
        lines.append("")

        lines.append("**目标级综合灯色结论**")
        lines.append("")
        lines.append(_render_conclusion_sentence(lamp_color, g.get("conclusionText", "")))
        lines.append("")
        lines.append(_render_lamp_block(lamp_color, g.get("goalJudgmentReason", "")))
        lines.append("")

        gd = os.path.join(goals_dir, gid)
        os.makedirs(gd, exist_ok=True)
        with open(os.path.join(gd, "goal_report.md"), "w", encoding="utf-8") as f:
            f.write("\n".join(lines))

    # --- Render excluded_goals.md ---
    if excluded:
        ex_lines = ["#### 未参与自查目标说明\n"]
        for g in excluded:
            gi = g.get("goalInfo", {})
            ex_lines.append(f'- **{gi.get("fullLevelNumber", "")}｜{gi.get("name", "")}**：★ 未启动 — {gi.get("excludeReason", "")}')
        ex_lines.append("")
        with open(os.path.join(wd, "excluded_goals.md"), "w", encoding="utf-8") as f:
            f.write("\n".join(ex_lines))

    # --- Render evidence_ledger.md from all goal JSONs ---
    all_reports = {}
    for g in participating:
        for r in g.get("evidence", {}).get("reports", []):
            rid = r.get("reportId", "")
            if rid and rid not in all_reports:
                all_reports[rid] = r

    primary_count = sum(1 for v in all_reports.values() if v.get("level") == "主证据")
    secondary_count = sum(1 for v in all_reports.values() if v.get("level") == "辅证")

    el_lines = [
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
            f"{n.get('nodeNumber', '')} {_strip_html(n.get('nodeName', ''))}" for n in info.get("nodes", [])
        )
        el_lines.append(
            f"| {info.get('rCode', '')} | 《{_strip_html(info.get('title', ''))}》 | {info.get('level', '')} "
            f"| [查看汇报](huibao://view?id={rid}) | {nodes_str} |"
        )

    # --- Render A.3 from prev_month.json ---
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
            rp_lines.append(f"| {rp_code} | {type_desc} | 《{title}》 | [查看汇报](huibao://view?id={rid}) |")
    else:
        prev_data = {}

    el_lines.append("")
    el_lines.append("#### A.3 上月参考索引\n")
    if rp_lines:
        el_lines.append("**上月汇报：**\n")
        el_lines.append("| RP 编号 | 类型 | 标题 | 链接 |")
        el_lines.append("|---------|------|------|------|")
        el_lines.extend(rp_lines)

        eval_lines = []
        for ev in prev_data.get("evaluations", []):
            eval_md = ev.get("evaluationMarkdown", "")
            if eval_md:
                eval_lines.append(eval_md)
        el_lines.append("")
        if eval_lines:
            el_lines.append("**上月评价摘要：**\n")
            el_lines.extend(eval_lines)
        else:
            el_lines.append("**上月评价摘要：**\n")
            el_lines.append("上月无评价记录。")
    else:
        el_lines.append("首月汇报，无上月参考基线。")

    with open(os.path.join(wd, "evidence_ledger.md"), "w", encoding="utf-8") as f:
        f.write("\n".join(el_lines))

    # --- Render chapter3.md / chapter4.md (fixed templates) ---
    ch3_content = (
        "> 请在 [BP 系统](https://bp.xgjktech.com) 中查看年度结果预判评分。\n"
        "> AI 不参与评分，仅展示评分入口。\n"
    )
    with open(os.path.join(wd, "chapter3.md"), "w", encoding="utf-8") as f:
        f.write(ch3_content)

    ch4_content = (
        "> 请在 [BP 系统](https://bp.xgjktech.com) 中查看月度汇报入口。\n"
        "> 也可通过各举措下方的证据链接直接跳转汇报详情。\n"
    )
    with open(os.path.join(wd, "chapter4.md"), "w", encoding="utf-8") as f:
        f.write(ch4_content)

    # --- Render report_header.md ---
    total_goals = len(goal_jsons)
    header_lines = [
        f"# {args.month} BP 自查报告",
        "",
        f"> **报告周期**：{args.month}  ",
        f"> **参与目标**：{len(participating)} / {total_goals} 个  ",
        f"> **灯色分布**：🟢{lamp_counts['green']} 🟡{lamp_counts['yellow']} 🔴{lamp_counts['red']} ⚫{lamp_counts['black']}  ",
    ]
    if rp_lines:
        header_lines.append(f"> **上月基线**：{len(rp_lines)} 份参考报告  ")
    header_lines.append("")

    with open(os.path.join(wd, "report_header.md"), "w", encoding="utf-8") as f:
        f.write("\n".join(header_lines))

    # --- Assemble final report ---
    from types import SimpleNamespace
    assemble_args = SimpleNamespace(group_id=args.group_id, month=args.month, output=None)
    assemble_result = assemble_report(assemble_args)

    _log(f"Done! Full report rendered: {len(participating)} participating, {len(excluded)} excluded, {len(failed)} failed")
    return {
        "success": True,
        "participating": len(participating),
        "excluded": len(excluded),
        "failed": len(failed),
        "assembleResult": assemble_result,
    }


ACTION_MAP = {
    "init_work_dir": init_work_dir,
    "collect_monthly_overview": collect_monthly_overview,
    "collect_goal_progress": collect_goal_progress,
    "collect_previous_month_data": collect_previous_month_data,
    "build_goal_evidence": build_goal_evidence,
    "build_judgment_input": build_judgment_input,
    "aggregate_lamp_colors": aggregate_lamp_colors,
    "build_evidence_ledger": build_evidence_ledger,
    "render_goal_report": render_goal_report,
    "render_conclusion": render_conclusion,
    "render_overview_table": render_overview_table,
    "render_report_header": render_report_header,
    "assemble_report": assemble_report,
    "save_openclaw_report": save_openclaw_report,
    "save_task_monthly_reading": save_task_monthly_reading,
    "update_report_status": update_report_status,
    "split_prev_report_by_goal": split_prev_report_by_goal,
    "assemble_goal_json": assemble_goal_json,
    "validate_goal_json": validate_goal_json,
    "fetch_goal_readings": fetch_goal_readings,
    "render_full_report": render_full_report,
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
