#!/usr/bin/env python3
"""Monthly Report API CLI — Skill B (bp-report-assembler).

Usage:
    python monthly_report_api.py <action> [options]

Actions:
    init_work_dir               Initialize per-run working directory
    collect_monthly_overview     Fetch task tree + goal list -> overview.json
    collect_previous_month_data  Aggregate previous month's reports + evaluations
    fetch_goal_readings          Fetch all goal JSONs from remote API
    render_full_report           One-shot render + assemble entire report
    save_openclaw_report         Save report to BP system
    update_report_status         Update report generation status (0/1/2)

Environment:
    BP_OPEN_API_APP_KEY       Authentication key (required)
    BP_OPEN_API_BASE_URL      API base URL (optional, has default)
"""

import argparse
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


# ─── HTTP helpers ─────────────────────────────────────────────────

def _do_request(method, url, headers, params=None, json_body=None):
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


# ─── Text helpers ─────────────────────────────────────────────────

def _strip_html(html):
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
    """Strip unwanted HTML while preserving template-defined lamp/people-suggest tags."""
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


# ─── Task tree helpers ────────────────────────────────────────────

_SLIM_TASK_FIELDS = ("id", "name", "fullLevelNumber", "type", "reportCycle",
                     "planDateRange", "statusDesc", "periodId", "groupId")


def _slim_task_tree(node):
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
    ids = []
    for node in (nodes or []):
        nid = node.get("id")
        if nid:
            ids.append(str(nid))
        ids.extend(_collect_all_ids(node.get("children")))
    return ids


def _collect_goal_summary(nodes):
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


# ─── Working directory helpers ────────────────────────────────────

def _work_dir(group_id, month):
    custom = os.environ.get("BP_WORK_DIR", "").strip()
    if custom:
        return os.path.join(custom, f"bp_report_{group_id}_{month}")
    return f"/Users/openclaw-data/bp/bp_report_{group_id}_{month}"


# ─── Lamp rendering helpers ──────────────────────────────────────

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
    info = LAMP_COLOR_MAP.get(lamp_color, LAMP_COLOR_MAP["green"])
    return (f'结论一句话：<span style="color:{info["css"]}; font-weight:700;">'
            f'{info["emoji"]} {_lamp_label(lamp_color)}</span>：{text}')


def _lamp_label(lamp_color):
    labels = {"green": "绿灯", "yellow": "黄灯", "red": "红灯", "black": "黑灯"}
    return labels.get(lamp_color, "绿灯")


# ─── Sorting helpers ─────────────────────────────────────────────

def _fln_sort_key(fln):
    """Sort key for fullLevelNumber like P12717-1, P12717-2, P12717-12."""
    if not fln:
        return (0, "")
    parts = re.split(r'[-.]', fln)
    result = []
    for p in parts:
        if p.isdigit():
            result.append((0, int(p)))
        else:
            result.append((1, p))
    return tuple(result)


def _rcode_sort_key(rcode):
    """Sort key for R-codes like R1001, R2001, R12001."""
    if not rcode:
        return (0, 0)
    m = re.match(r'R(\d+)', rcode)
    if m:
        return (int(m.group(1)),)
    return (0, rcode)


# ═══════════════════════════════════════════════════════════════════
#  ACTION HANDLERS
# ═══════════════════════════════════════════════════════════════════


def init_work_dir(args):
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


# ─── collect_previous_month_data ──────────────────────────────────

def collect_previous_month_data(args):
    """Aggregate previous month's reports + evaluations as reference."""
    if not args.group_id:
        return {"error": "group_id is required for collect_previous_month_data"}
    if not args.month:
        return {"error": "month (YYYY-MM, the previous month) is required for collect_previous_month_data"}

    errors = []
    prev_month = args.month

    _log(f"Fetching monthly report list for {prev_month}...")
    reports_result = _request("GET", "/bp/monthly/report/listByMonth",
                              params={"groupId": args.group_id, "reportMonth": prev_month})

    report_items = []
    if reports_result.get("success"):
        report_items = reports_result.get("data") or []
        _log(f"Found {len(report_items)} report(s) for {prev_month}")
    else:
        errors.append({"step": "list_monthly_reports", "error": reports_result.get("error")})

    report_month = getattr(args, "report_month", None) or ""
    if report_month:
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

    _log(f"Fetching monthly evaluation for {prev_month}...")
    eval_result = _request("GET", "/bp/monthly/evaluation/query",
                           params={"groupId": args.group_id, "evaluationMonth": prev_month})

    evaluations = []
    if eval_result.get("success"):
        evaluations = eval_result.get("data") or []
        _log(f"Found {len(evaluations)} evaluation(s) for {prev_month}")
    else:
        errors.append({"step": "monthly_evaluation", "error": eval_result.get("error")})

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


# ─── fetch_goal_readings ─────────────────────────────────────────

def fetch_goal_readings(args):
    """Fetch all goal-level JSONs from remote via monthlyReading/get API."""
    if not args.group_id:
        return {"error": "group_id is required for fetch_goal_readings"}
    if not args.month:
        return {"error": "month (YYYY-MM) is required for fetch_goal_readings"}

    wd = _work_dir(args.group_id, args.month)
    overview_path = os.path.join(wd, "overview.json")
    if not os.path.isfile(overview_path):
        return {"error": f"overview.json not found: {overview_path}. Run collect_monthly_overview first."}

    with open(overview_path, "r", encoding="utf-8") as f:
        overview = json.load(f)

    goal_meta = {}
    goal_ids = []
    for goal in overview.get("goals", []):
        gid = str(goal.get("goalId", ""))
        if gid:
            goal_ids.append(gid)
            goal_meta[gid] = {
                "fullLevelNumber": goal.get("fullLevelNumber", ""),
                "name": goal.get("name", ""),
            }

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
            meta = goal_meta.get(gid, {})
            failed_json = {
                "$schema": "goal_analysis_v1",
                "goalId": gid,
                "groupId": str(args.group_id),
                "month": args.month,
                "goalInfo": {
                    "fullLevelNumber": meta.get("fullLevelNumber", ""),
                    "name": meta.get("name", ""),
                    "excluded": False,
                },
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

            gd = os.path.join(goals_dir, gid)
            os.makedirs(gd, exist_ok=True)
            meta = goal_meta.get(gid, {})
            failed_json = {
                "$schema": "goal_analysis_v1",
                "goalId": gid,
                "groupId": str(args.group_id),
                "month": args.month,
                "goalInfo": {
                    "fullLevelNumber": meta.get("fullLevelNumber", ""),
                    "name": meta.get("name", ""),
                    "excluded": False,
                },
                "failed": True,
                "failReason": "该月份无记录，Skill A 可能尚未运行",
            }
            with open(os.path.join(gd, "goal_complete.json"), "w", encoding="utf-8") as f:
                json.dump(failed_json, f, ensure_ascii=False, indent=2)
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

    Reads all goal JSONs, conclusion_data.json, and prev_month.json,
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
        for goal_id in os.listdir(goals_dir):
            gc_path = os.path.join(goals_dir, goal_id, "goal_complete.json")
            if os.path.isfile(gc_path):
                with open(gc_path, "r", encoding="utf-8") as f:
                    goal_jsons.append(json.load(f))

    if not goal_jsons:
        return {"error": "No goal_complete.json files found. Run fetch_goal_readings first."}

    goal_jsons.sort(key=lambda g: _fln_sort_key(g.get("goalInfo", {}).get("fullLevelNumber", "")))

    participating = [g for g in goal_jsons if not g.get("goalInfo", {}).get("excluded") and not g.get("failed")]
    excluded = [g for g in goal_jsons if g.get("goalInfo", {}).get("excluded")]
    failed = [g for g in goal_jsons if g.get("failed")]

    lamp_counts = {"green": 0, "yellow": 0, "red": 0, "black": 0}
    for g in participating:
        color = g.get("lamp", {}).get("goalLamp", "black")
        lamp_counts[color] = lamp_counts.get(color, 0) + 1

    # ── Load prev_month.json for A.3 and header baseline ──
    prev_month_path = os.path.join(wd, "prev_month.json")
    prev_data = {}
    if os.path.isfile(prev_month_path):
        with open(prev_month_path, "r", encoding="utf-8") as f:
            prev_data = json.load(f)

    rp_items = []
    for i, item in enumerate(prev_data.get("reports", []), 1):
        rp_items.append({
            "rpCode": f"RP{i:02d}",
            "reportRecordId": item.get("reportRecordId", ""),
            "title": item.get("title", ""),
            "typeDesc": item.get("reportTypeDesc", ""),
        })

    # ── Parse month for display ──
    try:
        year, mon = args.month.split("-")
        month_display = f"{year}年{int(mon)}月"
    except ValueError:
        month_display = args.month

    employee_name = getattr(args, "employee_name", None) or ""

    # period_name: if not provided, auto-infer from month (e.g., "2026年BP")
    period_name = getattr(args, "period_name", None) or ""
    if not period_name and args.month:
        try:
            year = args.month[:4]
            period_name = f"{year}年BP"
        except (ValueError, IndexError):
            period_name = ""

    # ── Render report_header.md ──
    if employee_name:
        title = f"# {employee_name} {month_display} BP自查报告"
    else:
        title = f"# {month_display} BP自查报告"

    header_lines = [title, ""]
    if period_name:
        header_lines.append(f"> 周期：`{period_name}`")
    if employee_name:
        header_lines.append(f"> 节点：`{employee_name}`")

    if rp_items:
        rp_refs = "、".join(
            f'[{rp["rpCode"]}](huibao://view?id={rp["reportRecordId"]})'
            for rp in rp_items
        )
        header_lines.append(f"> 基线：已参考上月 {rp_refs} 及上月评价（详见附录 A.3）")
    else:
        header_lines.append("> 基线：首月，无基线")

    header_lines.append("> 证据说明：本报告中 R 编号（如 R0101）为当月证据引用，RP 编号（如 RP01）为上月参考引用，点击均可直接查看对应汇报详情。")
    header_lines.append("> 解释口径：灯色按目标级综合判断。")
    header_lines.append("")

    with open(os.path.join(wd, "report_header.md"), "w", encoding="utf-8") as f:
        f.write("\n".join(header_lines))

    # ── Render overview_table.md ──
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

    # ── Render conclusion.md ──
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

    # ── Render each goal_report.md from JSON ──
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
        lines.append(f'差异点：{c.get("gap") or "无"}  ')
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

    # ── Render excluded_goals.md ──
    if excluded:
        ex_lines = ["#### 未参与自查目标说明\n"]
        for g in excluded:
            gi = g.get("goalInfo", {})
            ex_lines.append(f'- **{gi.get("fullLevelNumber", "")}｜{gi.get("name", "")}**：★ 未启动 — {gi.get("excludeReason", "")}')
        ex_lines.append("")
        with open(os.path.join(wd, "excluded_goals.md"), "w", encoding="utf-8") as f:
            f.write("\n".join(ex_lines))

    # ── Render evidence_ledger.md from all goal JSONs ──
    all_reports = {}
    for g in participating:
        for r in g.get("evidence", {}).get("reports", []):
            rid = r.get("reportId", "")
            if rid and rid not in all_reports:
                all_reports[rid] = r

    sorted_reports = sorted(all_reports.values(), key=lambda r: _rcode_sort_key(r.get("rCode", "")))

    primary_count = sum(1 for v in sorted_reports if v.get("level") == "主证据")
    secondary_count = sum(1 for v in sorted_reports if v.get("level") == "辅证")

    el_lines = [
        "### 附录：证据索引\n",
        "#### A.1 统计摘要\n",
        f"- 原始工作汇报：{len(sorted_reports)} 份",
        f"- 经批量通知归并后最终采纳：{len(sorted_reports)} 份",
        f"- 其中本人主证据：{primary_count} 份、他人关联辅证：{secondary_count} 份\n",
        "#### A.2 证据索引表\n",
        "| R 编号 | 汇报标题 | 证据级别 | 汇报链接 | 关联节点 |",
        "|--------|---------|---------|---------|---------|",
    ]
    for info in sorted_reports:
        nodes_str = " / ".join(
            f"{n.get('nodeNumber', '')} {_strip_html(n.get('nodeName', ''))}" for n in info.get("nodes", [])
        )
        el_lines.append(
            f"| {info.get('rCode', '')} | 《{_strip_html(info.get('title', ''))}》 | {info.get('level', '')} "
            f"| [查看汇报](huibao://view?id={info.get('reportId', '')}) | {nodes_str} |"
        )

    # ── Render A.3 from prev_month.json ──
    el_lines.append("")
    el_lines.append("#### A.3 上月参考索引\n")
    if rp_items:
        el_lines.append("**上月汇报：**\n")
        el_lines.append("| RP 编号 | 类型 | 标题 | 链接 |")
        el_lines.append("|---------|------|------|------|")
        for rp in rp_items:
            el_lines.append(f"| {rp['rpCode']} | {rp['typeDesc']} | 《{rp['title']}》 | [查看汇报](huibao://view?id={rp['reportRecordId']}) |")

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

    # ── Render chapter3.md / chapter4.md (correct template links) ──
    ch3_content = (
        f"[点击进入本月：年度结果预判评分]"
        f"(https://sg-al-cwork-web.mediportal.com.cn/BP-manager/web/dist/#/monthly-review/self"
        f"?groupId={args.group_id}&month={args.month})\n"
    )
    with open(os.path.join(wd, "chapter3.md"), "w", encoding="utf-8") as f:
        f.write(ch3_content)

    ch4_content = (
        f"[点击进入查看系统月度汇报]"
        f"(https://sg-cwork-web.mediportal.com.cn/BP-manager/web/dist/#/MonthlyReportDashboard"
        f"?groupId={args.group_id})\n"
    )
    with open(os.path.join(wd, "chapter4.md"), "w", encoding="utf-8") as f:
        f.write(ch4_content)

    # ── Assemble final report ──
    assemble_result = _assemble_report(wd, goals_dir)

    _log(f"Done! Full report rendered: {len(participating)} participating, {len(excluded)} excluded, {len(failed)} failed")
    return {
        "success": True,
        "participating": len(participating),
        "excluded": len(excluded),
        "failed": len(failed),
        "assembleResult": assemble_result,
    }


# ─── Internal: assemble report ──────────────────────────────────

def _read_md(path, fallback=""):
    if os.path.isfile(path):
        with open(path, "r", encoding="utf-8") as f:
            return f.read()
    _log(f"Warning: file not found {path}, using fallback")
    return fallback


def _assemble_report(wd, goals_dir):
    """Splice final report from intermediate Markdown artifacts."""
    parts = []

    parts.append(_read_md(os.path.join(wd, "report_header.md"), "# BP自查报告\n"))
    parts.append("\n---\n")

    parts.append("### 1. 总体自查结论\n\n")
    conclusion = _read_md(os.path.join(wd, "conclusion.md"))
    if conclusion:
        parts.append(conclusion)
        parts.append("\n---\n")

    parts.append("### 2. 目标级自查明细\n")

    overview = _read_md(os.path.join(wd, "overview_table.md"))
    if overview:
        parts.append("#### 2.1 目标清单总览\n")
        parts.append(overview)
        parts.append("\n")

    parts.append("#### 2.2 目标明细\n")

    goal_count = 0
    if os.path.isdir(goals_dir):
        goal_dirs_with_fln = []
        for goal_id_dir in os.listdir(goals_dir):
            report_path = os.path.join(goals_dir, goal_id_dir, "goal_report.md")
            gc_path = os.path.join(goals_dir, goal_id_dir, "goal_complete.json")
            if os.path.isfile(report_path):
                fln = ""
                if os.path.isfile(gc_path):
                    try:
                        with open(gc_path, "r", encoding="utf-8") as f:
                            gc = json.load(f)
                        fln = gc.get("goalInfo", {}).get("fullLevelNumber", "")
                    except Exception:
                        pass
                goal_dirs_with_fln.append((fln, goal_id_dir, report_path))

        goal_dirs_with_fln.sort(key=lambda x: _fln_sort_key(x[0]))

        for _, _, report_path in goal_dirs_with_fln:
            with open(report_path, "r", encoding="utf-8") as f:
                parts.append(f.read())
            parts.append("\n")
            goal_count += 1

    excluded_path = os.path.join(wd, "excluded_goals.md")
    if os.path.isfile(excluded_path):
        parts.append(_read_md(excluded_path))
        parts.append("\n")

    parts.append("\n---\n")

    ch3 = _read_md(os.path.join(wd, "chapter3.md"))
    if ch3:
        parts.append("### 3. 年度结果预判评分\n\n")
        parts.append(ch3)
        parts.append("\n---\n")

    ch4 = _read_md(os.path.join(wd, "chapter4.md"))
    if ch4:
        parts.append("### 4. 月度汇报入口\n\n")
        parts.append(ch4)
        parts.append("\n---\n")

    ledger = _read_md(os.path.join(wd, "evidence_ledger.md"))
    if ledger:
        parts.append(ledger)

    final_report = "\n".join(parts)
    final_report = _strip_residual_html(final_report)

    output_path = os.path.join(wd, "report_selfcheck.md")
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(final_report)

    _log(f"Done! Final report assembled: {output_path} ({goal_count} goals, {len(final_report)} chars)")
    return {"success": True, "outputFile": output_path, "goalCount": goal_count, "charCount": len(final_report)}


# ─── save_openclaw_report ─────────────────────────────────────────

def save_openclaw_report(args):
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


# ─── update_report_status ─────────────────────────────────────────

def update_report_status(args):
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


# ═══════════════════════════════════════════════════════════════════
#  CLI ENTRY POINT
# ═══════════════════════════════════════════════════════════════════

ACTION_MAP = {
    "init_work_dir": init_work_dir,
    "collect_monthly_overview": collect_monthly_overview,
    "collect_previous_month_data": collect_previous_month_data,
    "fetch_goal_readings": fetch_goal_readings,
    "render_full_report": render_full_report,
    "save_openclaw_report": save_openclaw_report,
    "update_report_status": update_report_status,
}


def main():
    parser = argparse.ArgumentParser(
        description="Skill B — BP Report Assembler CLI",
    )
    parser.add_argument("action", choices=ACTION_MAP.keys(), help="The action to perform")
    parser.add_argument("--group_id", help="Personal group ID")
    parser.add_argument("--month", help="Target month YYYY-MM")
    parser.add_argument("--output", help="Output file path")
    parser.add_argument("--report_month", help="The actual report month (for collect_previous_month_data)")
    parser.add_argument("--content_file", help="Path to content file (for save_openclaw_report)")
    parser.add_argument("--status", help="Generate status: 0=generating, 1=success, 2=failed")
    parser.add_argument("--fail_reason", help="Failure reason (for update_report_status, required when status=2)")
    parser.add_argument("--employee_name", help="Employee name (for render_full_report header)")
    parser.add_argument("--period_name", help="BP period name (for render_full_report header)")

    args = parser.parse_args()

    result = ACTION_MAP[args.action](args)

    print(json.dumps(result, ensure_ascii=False, indent=2))

    if result.get("error"):
        sys.exit(1)


if __name__ == "__main__":
    main()
