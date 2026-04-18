#!/usr/bin/env python3
"""Monthly Report API CLI — fetch report content, collect monthly data, and send reports.

Usage:
    python monthly_report_api.py <action> [options]

Actions:
    collect_monthly_overview    Fetch task tree + goal list (lightweight, per-goal workflow step 1)
    collect_goal_data           Collect BP detail + reports for a single goal (per-goal workflow step 2)
    collect_monthly_data        [Legacy] Aggregate all BP data + reports into a single JSON
    collect_previous_month_data Aggregate previous month's reports + evaluations as reference context
    get_report_content          Get report body content by report ID
    save_draft                  Save monthly report as draft via draftBox API
    save_monthly_report         Save monthly report to BP system (2.22 saveMonthlyReport)
    update_report_status        Update monthly report generation status (0=generating, 1=success, 2=failed)

Environment:
    BP_OPEN_API_APP_KEY       Authentication key (required)
    BP_OPEN_API_BASE_URL      API base URL (optional, has default)
"""

import argparse
import calendar
import json
import os
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
DEFAULT_SENDER_ID = "400002"
REPORT_CONTENT_MAX_CHARS = 2000
SEND_RETRY_DELAY_SECONDS = 60
QUERY_RETRY_DELAY_SECONDS = 60
QUERY_MAX_RETRIES = 1

CORP_ID_TO_SENDER = {
    "1509805893730611201": "400001",
    "1509805893730611202": "400002",
    "1515978849561276500": "400003",
}

SENDER_TO_APP_KEY = {
    "400001": "5xmsXv311OVq121d5hzb5yGJ6sO5AB04",
    "400002": "1xmsXv2yv11OVqkd3zb5yG441sO5AB04",
    "400003": "5xmsXvVyv11dskd5hzb5ys6ssswqAB04",
}
DEFAULT_SEND_APP_KEY = SENDER_TO_APP_KEY[DEFAULT_SENDER_ID]


def _log(msg):
    print(f"[progress] {msg}", file=sys.stderr)


def _resolve_sender(receiver_emp_id):
    """Look up the receiver's corpId and return (sender_id, app_key).

    Each AI assistant (sender) has its own appKey for sending reports.
    Falls back to DEFAULT_SENDER_ID / DEFAULT_SEND_APP_KEY on failure.
    """
    url = f"{BASE_URL}/cwork-user/employee/getEmployeeOrgInfo"
    headers = {"appKey": APP_KEY}

    for attempt in range(1 + QUERY_MAX_RETRIES):
        try:
            resp = requests.get(url, params={"empId": receiver_emp_id}, headers=headers, timeout=TIMEOUT)
            resp.raise_for_status()
            data = resp.json()
            if data.get("resultCode") == 1 and data.get("data"):
                corp_id = str(data["data"].get("corpId") or "")
                sender = CORP_ID_TO_SENDER.get(corp_id)
                if sender:
                    app_key = SENDER_TO_APP_KEY.get(sender, DEFAULT_SEND_APP_KEY)
                    _log(f"Resolved sender: receiver={receiver_emp_id} -> corpId={corp_id} -> sender={sender}")
                    return sender, app_key
                _log(f"Unknown corpId={corp_id} for receiver={receiver_emp_id}, using default sender={DEFAULT_SENDER_ID}")
                return DEFAULT_SENDER_ID, DEFAULT_SEND_APP_KEY

            rc = data.get("resultCode")
            is_retryable = rc in (401, 429) or (isinstance(rc, int) and rc >= 500)
            if is_retryable and attempt < QUERY_MAX_RETRIES:
                _log(f"Resolve sender got resultCode={rc}, waiting {QUERY_RETRY_DELAY_SECONDS}s before retry...")
                time.sleep(QUERY_RETRY_DELAY_SECONDS)
                continue

            _log(f"Failed to get org info for receiver={receiver_emp_id}: {data.get('resultMsg')}, "
                 f"using default sender={DEFAULT_SENDER_ID}")
        except requests.HTTPError as e:
            rc = e.response.status_code
            is_retryable = rc in (401, 429) or rc >= 500
            if is_retryable and attempt < QUERY_MAX_RETRIES:
                _log(f"Resolve sender got HTTP {rc}, waiting {QUERY_RETRY_DELAY_SECONDS}s before retry...")
                time.sleep(QUERY_RETRY_DELAY_SECONDS)
                continue
            _log(f"Error resolving sender for receiver={receiver_emp_id}: {e}, using default sender={DEFAULT_SENDER_ID}")
        except Exception as e:
            _log(f"Error resolving sender for receiver={receiver_emp_id}: {e}, using default sender={DEFAULT_SENDER_ID}")

    return DEFAULT_SENDER_ID, DEFAULT_SEND_APP_KEY


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


def _collect_goal_ids(nodes):
    """Collect IDs of top-level goal nodes (type contains '目标')."""
    ids = []
    for node in (nodes or []):
        ntype = node.get("type", "")
        if "目标" in ntype:
            nid = node.get("id")
            if nid:
                ids.append(str(nid))
    return ids


def _month_time_range(month_str):
    """Convert 'YYYY-MM' to (start, end) datetime strings."""
    year, month = int(month_str[:4]), int(month_str[5:7])
    last_day = calendar.monthrange(year, month)[1]
    return (f"{year:04d}-{month:02d}-01 00:00:00",
            f"{year:04d}-{month:02d}-{last_day:02d} 23:59:59")


def _truncate(text, max_chars=REPORT_CONTENT_MAX_CHARS):
    if text and len(text) > max_chars:
        return text[:max_chars] + " [...truncated]"
    return text


def _collect_goal_summary(nodes):
    """Extract summary info for each top-level goal from slim task tree."""
    goals = []
    for node in (nodes or []):
        ntype = node.get("type", "")
        if "目标" in ntype:
            goals.append({
                "goalId": str(node["id"]) if node.get("id") else None,
                "name": node.get("name", ""),
                "fullLevelNumber": node.get("fullLevelNumber", ""),
                "planDateRange": node.get("planDateRange", ""),
                "statusDesc": node.get("statusDesc", ""),
            })
    return goals


def _extract_ids_from_goal_detail(goal_detail):
    """Recursively extract all node IDs from a goal detail response.

    Handles both field naming conventions from the API:
    - keyResultList / keyResults for KR list
    - actionList / actions for action list
    """
    ids = []
    if not goal_detail:
        return ids
    gid = goal_detail.get("id")
    if gid:
        ids.append(str(gid))
    kr_list = goal_detail.get("keyResultList") or goal_detail.get("keyResults") or []
    for kr in kr_list:
        kid = kr.get("id")
        if kid:
            ids.append(str(kid))
        action_list = kr.get("actionList") or kr.get("actions") or []
        for action in action_list:
            aid = action.get("id")
            if aid:
                ids.append(str(aid))
    return ids


def _build_report_content(rd, truncate=True):
    """Build a report content dict from raw API response."""
    content_html = rd.get("contentHtml") or rd.get("content") or ""
    return {
        "reportId": str(rd.get("id") or rd.get("reportId") or ""),
        "title": rd.get("main", ""),
        "content": _truncate(content_html) if truncate else content_html,
        "contentType": rd.get("contentType", ""),
        "createTime": rd.get("createTime"),
        "authorEmpId": rd.get("writeEmpId") or rd.get("empId") or rd.get("authorEmpId") or rd.get("createBy"),
        "authorName": rd.get("writeEmpName") or rd.get("empName") or rd.get("authorName") or rd.get("createByName"),
    }


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

    output_path = args.output or f"/tmp/monthly_overview_{args.group_id}.json"
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    _log(f"Done! Overview written to {output_path} ({len(goals)} goals, {len(all_ids)} nodes)")
    return {"success": True, "outputFile": output_path, "stats": output["stats"]}


# ─── collect_goal_data ────────────────────────────────────────────

def collect_goal_data(args):
    """Collect BP detail + reports for a single goal (per-goal granularity).

    1. Fetch goal detail (with KRs and actions)
    2. Extract all node IDs under this goal
    3. Query reports for each node within the month
    4. Fetch full report content for all unique report IDs (no truncation)
    5. Build reverse index and per-task report data
    6. Write independent JSON file for this goal
    """
    if not args.goal_id:
        return {"error": "goal_id is required for collect_goal_data"}
    if not args.month:
        return {"error": "month (YYYY-MM) is required for collect_goal_data"}

    errors = []
    time_start, time_end = _month_time_range(args.month)

    _log(f"Fetching goal detail: {args.goal_id}")
    detail = _request("GET", "/bp/task/v2/getGoalAndKeyResult", params={"id": args.goal_id})
    if not detail.get("success"):
        return {"error": f"Failed to fetch goal detail: {detail.get('error')}"}

    goal_detail = detail["data"]
    node_ids = _extract_ids_from_goal_detail(goal_detail)
    _log(f"Goal has {len(node_ids)} nodes")

    task_report_ids = {}
    all_report_ids = set()
    page_size = 200
    for i, tid in enumerate(node_ids, 1):
        page_index = 1
        tid_biz_ids = []
        while True:
            body = {
                "taskId": tid,
                "pageIndex": page_index,
                "pageSize": page_size,
                "businessTimeStart": time_start,
                "businessTimeEnd": time_end,
            }
            result = _request("POST", "/bp/task/relation/pageAllReports", json_body=body)
            if result.get("success"):
                records = result["data"].get("list") or []
                for rec in records:
                    bid = rec.get("bizId")
                    if bid:
                        bid_str = str(bid)
                        tid_biz_ids.append({"bizId": bid_str, "type": rec.get("type", ""), "businessTime": rec.get("businessTime")})
                        all_report_ids.add(bid_str)
                if len(records) < page_size:
                    break
                page_index += 1
            else:
                errors.append({"step": "task_reports", "id": tid, "error": result.get("error")})
                break
        if tid_biz_ids:
            task_report_ids[tid] = tid_biz_ids

    _log(f"Found {len(all_report_ids)} unique reports across {len(task_report_ids)} nodes")

    report_contents = {}
    for i, rid in enumerate(sorted(all_report_ids), 1):
        if i % 10 == 0 or i == len(all_report_ids):
            _log(f"  fetching report content {i}/{len(all_report_ids)}")
        result = _request("GET", "/work-report/report/info", params={"reportId": rid})
        if result.get("success") and result["data"]:
            rc = _build_report_content(result["data"], truncate=False)
            rc["reportId"] = rid
            report_contents[rid] = rc
        else:
            errors.append({"step": "report_content", "id": rid, "error": result.get("error")})

    report_task_mapping = {}
    for tid, biz_entries in task_report_ids.items():
        for entry in biz_entries:
            bid = entry["bizId"]
            report_task_mapping.setdefault(bid, [])
            if tid not in report_task_mapping[bid]:
                report_task_mapping[bid].append(tid)

    reports_by_task = {}
    for tid, biz_entries in task_report_ids.items():
        task_reports = []
        for entry in biz_entries:
            bid = entry["bizId"]
            rc = report_contents.get(bid)
            if rc:
                task_reports.append({**rc, "type": entry.get("type", ""), "businessTime": entry.get("businessTime")})
        if task_reports:
            reports_by_task[tid] = task_reports

    group_id = getattr(args, "group_id", None) or ""

    output = {
        "goalId": args.goal_id,
        "groupId": group_id,
        "month": args.month,
        "collectTime": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "goalDetail": goal_detail,
        "uniqueReportMap": report_contents,
        "reportTaskMapping": report_task_mapping,
        "reports": reports_by_task,
        "stats": {
            "nodeCount": len(node_ids),
            "uniqueReportCount": len(all_report_ids),
            "fetchedReportContents": len(report_contents),
        },
    }
    if errors:
        output["errors"] = errors

    output_path = args.output or f"/tmp/goal_data_{group_id}_{args.goal_id}.json"
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    _log(f"Done! Goal data written to {output_path}")
    return {"success": True, "outputFile": output_path, "stats": output["stats"]}


# ─── collect_monthly_data (legacy, kept for backward compatibility) ──

def collect_monthly_data(args):
    """Aggregate all BP structure + report data for one employee/month.

    Performs the following in a single invocation:
    1. Fetch task tree for the group
    2. Fetch goal details for each top-level goal
    3. Query reports for every task node within the month
    4. Fetch report content for all unique report IDs
    5. Write aggregated JSON to --output file
    """
    if not args.group_id:
        return {"error": "group_id is required for collect_monthly_data"}
    if not args.month:
        return {"error": "month (YYYY-MM) is required for collect_monthly_data"}

    errors = []
    time_start, time_end = _month_time_range(args.month)

    # Step 1: task tree
    _log("Fetching task tree...")
    tree_result = _request("GET", "/bp/task/v2/getSimpleTree", params={"groupId": args.group_id})
    if not tree_result.get("success"):
        return {"error": f"Failed to fetch task tree: {tree_result.get('error')}"}

    raw_tree = tree_result["data"]
    task_tree = _slim_task_tree(raw_tree) if raw_tree else []
    all_ids = _collect_all_ids(task_tree)
    goal_ids = _collect_goal_ids(task_tree)
    _log(f"Task tree: {len(all_ids)} nodes, {len(goal_ids)} goals")

    # Step 2: goal details
    goal_details = {}
    for i, gid in enumerate(goal_ids, 1):
        _log(f"Fetching goal detail {i}/{len(goal_ids)}: {gid}")
        detail = _request("GET", "/bp/task/v2/getGoalAndKeyResult", params={"id": gid})
        if detail.get("success"):
            goal_details[gid] = detail["data"]
        else:
            errors.append({"step": "goal_detail", "id": gid, "error": detail.get("error")})

    # Step 3: query reports for each task node
    _log(f"Querying reports for {len(all_ids)} task nodes...")
    task_report_ids = {}
    all_report_ids = set()
    page_size = 200

    for i, tid in enumerate(all_ids, 1):
        if i % 10 == 0 or i == len(all_ids):
            _log(f"  reports query {i}/{len(all_ids)}")
        page_index = 1
        tid_biz_ids = []
        while True:
            body = {
                "taskId": tid,
                "pageIndex": page_index,
                "pageSize": page_size,
                "businessTimeStart": time_start,
                "businessTimeEnd": time_end,
            }
            result = _request("POST", "/bp/task/relation/pageAllReports", json_body=body)
            if result.get("success"):
                records = result["data"].get("list") or []
                for rec in records:
                    bid = rec.get("bizId")
                    if bid:
                        bid_str = str(bid)
                        tid_biz_ids.append({"bizId": bid_str, "type": rec.get("type", ""), "businessTime": rec.get("businessTime")})
                        all_report_ids.add(bid_str)
                if len(records) < page_size:
                    break
                page_index += 1
            else:
                errors.append({"step": "task_reports", "id": tid, "error": result.get("error")})
                break
        if tid_biz_ids:
            task_report_ids[tid] = tid_biz_ids

    _log(f"Found {len(all_report_ids)} unique reports across {len(task_report_ids)} tasks")

    # Step 4: fetch report content for all unique report IDs
    report_contents = {}
    report_id_list = sorted(all_report_ids)
    for i, rid in enumerate(report_id_list, 1):
        if i % 10 == 0 or i == len(report_id_list):
            _log(f"  fetching report content {i}/{len(report_id_list)}")
        result = _request("GET", "/work-report/report/info", params={"reportId": rid})
        if result.get("success") and result["data"]:
            rc = _build_report_content(result["data"], truncate=False)
            rc["reportId"] = rid
            report_contents[rid] = rc
        else:
            errors.append({"step": "report_content", "id": rid, "error": result.get("error")})

    # Step 5: build reverse index — reportId -> list of associated taskIds
    report_task_mapping = {}
    for tid, biz_entries in task_report_ids.items():
        for entry in biz_entries:
            bid = entry["bizId"]
            report_task_mapping.setdefault(bid, [])
            if tid not in report_task_mapping[bid]:
                report_task_mapping[bid].append(tid)

    # Step 6: assemble per-task report data (backward-compatible)
    reports_by_task = {}
    for tid, biz_entries in task_report_ids.items():
        task_reports = []
        for entry in biz_entries:
            bid = entry["bizId"]
            rc = report_contents.get(bid)
            if rc:
                task_reports.append({
                    **rc,
                    "type": entry.get("type", ""),
                    "businessTime": entry.get("businessTime"),
                })
        if task_reports:
            reports_by_task[tid] = task_reports

    # Step 7: content dedup — group reports with near-identical content
    _seen_titles = {}
    unique_work_items = 0
    for rid, rc in report_contents.items():
        title_key = (rc.get("title") or "").strip()
        if title_key and title_key in _seen_titles:
            _seen_titles[title_key].append(rid)
        else:
            _seen_titles[title_key or rid] = [rid]
            unique_work_items += 1

    # Step 8: build output
    output = {
        "groupId": args.group_id,
        "month": args.month,
        "collectTime": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "taskTree": task_tree,
        "goalDetails": goal_details,
        "uniqueReportMap": report_contents,
        "reportTaskMapping": report_task_mapping,
        "reports": reports_by_task,
        "stats": {
            "totalTasks": len(all_ids),
            "totalGoals": len(goal_ids),
            "totalReportQueries": len(task_report_ids),
            "rawReportCount": sum(len(v) for v in task_report_ids.values()),
            "uniqueReportCount": len(all_report_ids),
            "fetchedReportContents": len(report_contents),
            "uniqueWorkItemCount": unique_work_items,
        },
    }
    if errors:
        output["errors"] = errors

    output_path = args.output
    if not output_path:
        output_path = f"/tmp/monthly_data_{args.group_id}.json"

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    _log(f"Done! Output written to {output_path}")
    return {"success": True, "outputFile": output_path, "stats": output["stats"]}


def get_report_content(args):
    """GET /work-report/report/info?reportId={id}"""
    if not args.report_id:
        return {"error": "report_id is required for get_report_content"}
    return _request("GET", "/work-report/report/info", params={"reportId": args.report_id})


def _do_save_draft(url, headers, body):
    """Execute the actual HTTP POST for save_draft."""
    resp = requests.post(url, json=body, headers=headers, timeout=TIMEOUT)
    resp.raise_for_status()
    data = resp.json()
    if data.get("resultCode") != 1:
        return {"error": data.get("resultMsg", "Unknown API error"), "resultCode": data.get("resultCode")}
    return {"success": True, "data": data.get("data")}


def _is_rate_limited(result):
    """Check if the error indicates API rate limiting (resultCode 401 with valid params)."""
    return result.get("resultCode") == 401


def _should_retry(result):
    """Determine if save_draft should retry based on error type."""
    error_msg = str(result.get("error", ""))
    if "汇报人ID有误" in error_msg:
        return "emp_id_error"
    if _is_rate_limited(result):
        return "rate_limited"
    return None


def save_draft(args):
    """POST /work-report/draftBox/saveOrUpdate — save monthly report as draft.

    Uses the built-in robot app key, NOT the user's BP_OPEN_API_APP_KEY.
    Retryable errors (rate limit 401, "汇报人ID有误"):
    verify key, wait 60s, retry once.
    """
    if not args.receiver_emp_id:
        return {"error": "receiver_emp_id is required for save_draft"}
    if not args.title:
        return {"error": "title is required for save_draft"}
    if not args.content_file:
        return {"error": "content_file is required for save_draft"}

    content_path = args.content_file
    if not os.path.isfile(content_path):
        return {"error": f"Content file not found: {content_path}"}

    with open(content_path, "r", encoding="utf-8") as f:
        content = f.read()

    if not content.strip():
        return {"error": "Content file is empty"}

    first_receiver = args.receiver_emp_id.split(",")[0].strip()
    if args.sender_id:
        sender_id = args.sender_id
        send_app_key = SENDER_TO_APP_KEY.get(sender_id, DEFAULT_SEND_APP_KEY)
    else:
        sender_id, send_app_key = _resolve_sender(first_receiver)

    receiver_list = [
        {"empId": rid.strip()}
        for rid in args.receiver_emp_id.split(",") if rid.strip()
    ]

    body = {
        "main": args.title,
        "contentHtml": content,
        "contentType": "markdown",
        "comeFrom": "BP-API调用",
        "templateId": 2044631241659035650,
        "flowType": "merge_template_node",
        "reportLevelList": [
            {
                "level": 1,
                "levelUserList": receiver_list,
                "nodeName": "建议",
                "type": "suggest",
            },
            {
                 "level": 2,
                 "levelUserList": receiver_list,
                 "nodeName": "建议",
                 "type": "suggest",
             }
        ],
    }

    copy_ids = getattr(args, "copy_emp_ids", None)
    if copy_ids:
        body["copyEmpIdList"] = [cid.strip() for cid in copy_ids.split(",") if cid.strip()]

    url = f"{BASE_URL}/work-report/draftBox/saveOrUpdate"
    headers = {"appKey": send_app_key, "Content-Type": "application/json"}
    _log(f"Saving draft with sender={sender_id}, appKey={send_app_key[:8]}...")

    try:
        result = _do_save_draft(url, headers, body)
    except requests.RequestException as exc:
        return {"error": f"Network error: {exc}"}

    retry_reason = _should_retry(result) if result.get("error") else None
    if retry_reason:
        if retry_reason == "emp_id_error":
            _log(f"Got '汇报人ID有误' for empId={args.receiver_emp_id}. "
                 f"Verifying appKey matches sender={sender_id}...")
        elif retry_reason == "rate_limited":
            _log(f"Got resultCode=401 (rate limited) for empId={args.receiver_emp_id}. "
                 f"Params look correct, treating as rate limit...")

        expected_key = SENDER_TO_APP_KEY.get(sender_id, DEFAULT_SEND_APP_KEY)
        if headers["appKey"] != expected_key:
            _log(f"Key mismatch detected, switching to correct key for sender={sender_id}")
            headers["appKey"] = expected_key

        _log(f"Waiting {SEND_RETRY_DELAY_SECONDS}s before retry...")
        time.sleep(SEND_RETRY_DELAY_SECONDS)
        try:
            result = _do_save_draft(url, headers, body)
            if result.get("success"):
                _log("Retry succeeded.")
            else:
                _log(f"Retry failed: {result.get('error')}")
        except requests.RequestException as exc:
            return {"error": f"Network error on retry: {exc}"}

    if result.get("success"):
        _log(f"Draft saved successfully. Receiver: {args.receiver_emp_id}, Sender: {sender_id}")

    return result


def save_monthly_report(args):
    """POST /bp/monthly/report/save — persist report to BP system.

    Uses the data-query APP_KEY (not the robot key),
    because the BP monthly report save API requires user-level permission.
    reportRecordId is required — pass the id returned by save_draft.
    """
    if not args.group_id:
        return {"error": "group_id is required for save_monthly_report"}
    if not args.month:
        return {"error": "month is required for save_monthly_report"}
    if not args.content_file:
        return {"error": "content_file is required for save_monthly_report"}
    if not getattr(args, "report_record_id", None):
        return {"error": "report_record_id is required for save_monthly_report (pass the id returned by save_draft)"}

    content_path = args.content_file
    if not os.path.isfile(content_path):
        return {"error": f"Content file not found: {content_path}"}

    with open(content_path, "r", encoding="utf-8") as f:
        content = f.read()

    if not content.strip():
        return {"error": "Content file is empty"}

    if not APP_KEY:
        return {"error": "BP_OPEN_API_APP_KEY is not configured. Required for save_monthly_report."}

    body = {
        "groupId": args.group_id,
        "reportContent": content,
        "reportMonth": args.month,
        "reportRecordId": args.report_record_id,
    }

    _log(f"Saving monthly report: groupId={args.group_id}, month={args.month}")
    result = _request("POST", "/bp/monthly/report/save", json_body=body)

    if result.get("success"):
        _log(f"Monthly report saved. groupId: {args.group_id}, month: {args.month}, "
             f"reportId: {result['data']}")

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
    report_contents = []
    for item in report_items:
        rid = item.get("reportRecordId")
        type_desc = item.get("reportTypeDesc", "")
        if not rid:
            continue
        _log(f"Fetching report content: {type_desc} (id={rid})")
        content_result = _request("GET", "/work-report/report/info", params={"reportId": str(rid)})
        if content_result.get("success") and content_result.get("data"):
            rd = content_result["data"]
            content_html = rd.get("contentHtml") or rd.get("content") or ""
            report_contents.append({
                "reportTypeDesc": type_desc,
                "reportRecordId": str(rid),
                "title": rd.get("main", ""),
                "content": content_html,
                "createTime": rd.get("createTime"),
            })
        else:
            errors.append({"step": "report_content", "id": str(rid), "error": content_result.get("error")})

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

    output_path = args.output
    if not output_path:
        output_path = f"/tmp/prev_month_data_{args.group_id}.json"

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    _log(f"Done! Previous month data written to {output_path}")
    return {"success": True, "outputFile": output_path, "stats": output["stats"]}


ACTION_MAP = {
    "collect_monthly_overview": collect_monthly_overview,
    "collect_goal_data": collect_goal_data,
    "collect_monthly_data": collect_monthly_data,
    "collect_previous_month_data": collect_previous_month_data,
    "get_report_content": get_report_content,
    "save_draft": save_draft,
    "save_monthly_report": save_monthly_report,
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
    parser.add_argument("--goal_id", help="Goal ID (for collect_goal_data)")
    parser.add_argument("--month", help="Target month YYYY-MM")
    parser.add_argument("--output", help="Output JSON file path")
    parser.add_argument("--report_id", help="Report ID (for get_report_content)")
    parser.add_argument("--receiver_emp_id", help="Receiver employee ID (for save_draft)")
    parser.add_argument("--title", help="Report title (for save_draft)")
    parser.add_argument("--content_file", help="Path to markdown content file (for save_draft)")
    parser.add_argument("--sender_id", help=f"Sender system user ID (default: {DEFAULT_SENDER_ID})")
    parser.add_argument("--report_record_id", help="Report record ID from save_draft (for save_monthly_report)")
    parser.add_argument("--copy_emp_ids", help="Comma-separated copy employee IDs (for save_draft)")
    parser.add_argument("--status", help="Generate status: 0=generating, 1=success, 2=failed (for update_report_status)")
    parser.add_argument("--fail_reason", help="Failure reason (for update_report_status, required when status=2)")

    args = parser.parse_args()

    result = ACTION_MAP[args.action](args)

    print(json.dumps(result, ensure_ascii=False, indent=2))

    if result.get("error"):
        sys.exit(1)


if __name__ == "__main__":
    main()
