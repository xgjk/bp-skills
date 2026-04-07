#!/usr/bin/env python3
"""Monthly Report API CLI — fetch report content, collect monthly data, and send reports.

Usage:
    python monthly_report_api.py <action> [options]

Actions:
    collect_monthly_data  Aggregate all BP data + reports for one employee/month into a single JSON
    get_report_content    Get report body content by report ID
    send_report           Send monthly report via work-report API
    save_monthly_report   Save monthly report to BP system (2.22 saveMonthlyReport)

Environment:
    BP_OPEN_API_APP_KEY       Authentication key (required)
    BP_OPEN_API_BASE_URL      API base URL (optional, has default)
"""

import argparse
import calendar
import json
import os
import sys
from datetime import datetime

import requests

BASE_URL = os.environ.get(
    "BP_OPEN_API_BASE_URL",
    "https://sg-al-cwork-web.mediportal.com.cn/open-api",
)
APP_KEY = os.environ.get("BP_OPEN_API_APP_KEY", "")
SEND_REPORT_APP_KEY = "1xmsXv2yv11OVqkd3zb5yG441sO5AB04"

TIMEOUT = 30
DEFAULT_SENDER_ID = "400002"
REPORT_CONTENT_MAX_CHARS = 2000


def _log(msg):
    print(f"[progress] {msg}", file=sys.stderr)


def _request(method, path, *, params=None, json_body=None):
    if not APP_KEY:
        return {"error": "BP_OPEN_API_APP_KEY is not configured. Set it as an environment variable."}

    url = f"{BASE_URL}{path}"
    headers = {"appKey": APP_KEY}

    try:
        if method == "GET":
            resp = requests.get(url, params=params, headers=headers, timeout=TIMEOUT)
        else:
            headers["Content-Type"] = "application/json"
            resp = requests.post(url, params=params, json=json_body, headers=headers, timeout=TIMEOUT)

        resp.raise_for_status()
        data = resp.json()

        if data.get("resultCode") != 1:
            return {"error": data.get("resultMsg", "Unknown API error"), "resultCode": data.get("resultCode")}

        return {"success": True, "data": data.get("data")}

    except requests.HTTPError as e:
        return {"error": f"HTTP {e.response.status_code}: {e.response.text}"}
    except Exception as e:
        return {"error": str(e)}


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


# ─── collect_monthly_data ─────────────────────────────────────────

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

    for i, tid in enumerate(all_ids, 1):
        if i % 10 == 0 or i == len(all_ids):
            _log(f"  reports query {i}/{len(all_ids)}")
        body = {
            "taskId": tid,
            "pageIndex": 1,
            "pageSize": 200,
            "businessTimeStart": time_start,
            "businessTimeEnd": time_end,
        }
        result = _request("POST", "/bp/task/relation/pageAllReports", json_body=body)
        if result.get("success"):
            records = result["data"].get("list") or []
            biz_ids = []
            for rec in records:
                bid = rec.get("bizId")
                if bid:
                    bid_str = str(bid)
                    biz_ids.append({"bizId": bid_str, "type": rec.get("type", ""), "businessTime": rec.get("businessTime")})
                    all_report_ids.add(bid_str)
            if biz_ids:
                task_report_ids[tid] = biz_ids
        else:
            errors.append({"step": "task_reports", "id": tid, "error": result.get("error")})

    _log(f"Found {len(all_report_ids)} unique reports across {len(task_report_ids)} tasks")

    # Step 4: fetch report content for all unique report IDs
    report_contents = {}
    report_id_list = sorted(all_report_ids)
    for i, rid in enumerate(report_id_list, 1):
        if i % 10 == 0 or i == len(report_id_list):
            _log(f"  fetching report content {i}/{len(report_id_list)}")
        result = _request("GET", "/work-report/report/info", params={"reportId": rid})
        if result.get("success") and result["data"]:
            rd = result["data"]
            content_html = rd.get("contentHtml") or rd.get("content") or ""
            report_contents[rid] = {
                "reportId": rid,
                "title": rd.get("main", ""),
                "content": _truncate(content_html),
                "contentType": rd.get("contentType", ""),
                "createTime": rd.get("createTime"),
                "authorEmpId": rd.get("empId") or rd.get("authorEmpId") or rd.get("createBy"),
                "authorName": rd.get("empName") or rd.get("authorName") or rd.get("createByName"),
            }
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


def send_report(args):
    """POST /work-report/report/record/submit — send monthly report.

    Mirrors MonthlyReportGenerateService.sendMonthlyReport() logic:
    - contentType: markdown
    - reportRecordType: 4 (AI report)
    - Level 1: read (employee self)
    - sender: BP system user (default 400002)
    """
    if not args.receiver_emp_id:
        return {"error": "receiver_emp_id is required for send_report"}
    if not args.title:
        return {"error": "title is required for send_report"}
    if not args.content_file:
        return {"error": "content_file is required for send_report"}

    content_path = args.content_file
    if not os.path.isfile(content_path):
        return {"error": f"Content file not found: {content_path}"}

    with open(content_path, "r", encoding="utf-8") as f:
        content = f.read()

    if not content.strip():
        return {"error": "Content file is empty"}

    sender_id = args.sender_id or DEFAULT_SENDER_ID

    body = {
        "main": args.title,
        "contentHtml": content,
        "contentType": "markdown",
        "reportLevelList": [
            {
                "level": 1,
                "levelUserList": [{"empId": args.receiver_emp_id}],
                "nodeName": "传阅",
                "type": "read",
            }
        ],
    }

    url = f"{BASE_URL}/work-report/report/record/submit"
    headers = {"appKey": SEND_REPORT_APP_KEY, "Content-Type": "application/json"}

    try:
        resp = requests.post(url, json=body, headers=headers, timeout=TIMEOUT)
        resp.raise_for_status()
        data = resp.json()
        if data.get("resultCode") != 1:
            return {"error": data.get("resultMsg", "Unknown API error"), "resultCode": data.get("resultCode")}
        result = {"success": True, "data": data.get("data")}
    except requests.RequestException as exc:
        return {"error": f"Network error: {exc}"}

    if result.get("success"):
        print(f"[info] Report sent successfully. Receiver: {args.receiver_emp_id}, Sender: {sender_id}",
              file=sys.stderr)

    return result


def save_monthly_report(args):
    """POST /bp/monthly/report/save — persist report to BP system.

    Uses the data-query APP_KEY (not the send-report robot key),
    because the BP monthly report save API requires user-level permission.
    """
    if not args.group_id:
        return {"error": "group_id is required for save_monthly_report"}
    if not args.month:
        return {"error": "month is required for save_monthly_report"}
    if not args.content_file:
        return {"error": "content_file is required for save_monthly_report"}

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
        "groupId": int(args.group_id),
        "reportContent": content,
        "reportMonth": args.month,
    }
    if getattr(args, "report_record_id", None):
        body["reportRecordId"] = int(args.report_record_id)

    url = f"{BASE_URL}/bp/monthly/report/save"
    headers = {"appKey": APP_KEY, "Content-Type": "application/json"}

    try:
        resp = requests.post(url, json=body, headers=headers, timeout=TIMEOUT)
        resp.raise_for_status()
        data = resp.json()
        if data.get("resultCode") != 1:
            return {"error": data.get("resultMsg", "Unknown API error"), "resultCode": data.get("resultCode")}
        result = {"success": True, "data": data.get("data")}
    except requests.RequestException as exc:
        return {"error": f"Network error: {exc}"}

    if result.get("success"):
        print(f"[info] Monthly report saved to BP system. groupId: {args.group_id}, month: {args.month}, "
              f"reportId: {result['data']}", file=sys.stderr)

    return result


ACTION_MAP = {
    "collect_monthly_data": collect_monthly_data,
    "get_report_content": get_report_content,
    "send_report": send_report,
    "save_monthly_report": save_monthly_report,
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
    parser.add_argument("--group_id", help="Personal group ID (for collect_monthly_data)")
    parser.add_argument("--month", help="Target month YYYY-MM (for collect_monthly_data)")
    parser.add_argument("--output", help="Output JSON file path (for collect_monthly_data)")
    parser.add_argument("--report_id", help="Report ID (for get_report_content)")
    parser.add_argument("--receiver_emp_id", help="Receiver employee ID (for send_report)")
    parser.add_argument("--title", help="Report title (for send_report)")
    parser.add_argument("--content_file", help="Path to markdown content file (for send_report)")
    parser.add_argument("--sender_id", help=f"Sender system user ID (default: {DEFAULT_SENDER_ID})")
    parser.add_argument("--report_record_id", help="Report record ID from send_report (for save_monthly_report)")

    args = parser.parse_args()

    result = ACTION_MAP[args.action](args)

    print(json.dumps(result, ensure_ascii=False, indent=2))

    if result.get("error"):
        sys.exit(1)


if __name__ == "__main__":
    main()
