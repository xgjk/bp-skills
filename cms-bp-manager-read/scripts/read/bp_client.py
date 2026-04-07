#!/usr/bin/env python3
"""
BP Open API 客户端（只读）

约束：
- 仅封装只读接口
- appKey 由运行时注入（依赖 cms-auth-skills），不在代码中硬编码、不回显
"""

import json
import os
import sys
import urllib.parse
import urllib.request
from typing import Any, Dict, List, Optional


def _configure_io_encoding() -> None:
    """
    兼容 LANG=en_US 等非 UTF-8 终端环境，避免中文输出/异常信息导致编码崩溃。
    """
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    try:
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass


class BPClient:
    def __init__(self, app_key: Optional[str] = None, base_url: Optional[str] = None):
        _configure_io_encoding()
        self.AppKey = app_key or os.getenv("BP_APP_KEY")
        self.BaseUrl = base_url or "https://sg-al-cwork-web.mediportal.com.cn/open-api"
        if not self.AppKey:
            raise ValueError("缺少 appKey，请通过 cms-auth-skills 注入或设置 BP_APP_KEY")

    def _request(self, method: str, path: str, params: Optional[Dict[str, Any]] = None, data: Any = None) -> Dict[str, Any]:
        url = f"{self.BaseUrl}{path}"
        headers = {"appKey": self.AppKey, "Content-Type": "application/json"}
        if params:
            # 显式指定 UTF-8，避免在非 UTF-8 locale 下中文被错误编码
            url = f"{url}?{urllib.parse.urlencode(params, encoding='utf-8', errors='strict')}"

        try:
            if method == "GET":
                req = urllib.request.Request(url, headers=headers)
                with urllib.request.urlopen(req, timeout=60) as resp:
                    return json.loads(resp.read().decode("utf-8"))
            if method == "POST":
                payload = json.dumps(data).encode("utf-8") if data is not None else None
                req = urllib.request.Request(url, headers=headers, data=payload, method="POST")
                with urllib.request.urlopen(req, timeout=60) as resp:
                    return json.loads(resp.read().decode("utf-8"))
            raise ValueError(f"不支持的 HTTP 方法：{method}")
        except Exception as exc:
            return {"resultCode": 0, "resultMsg": str(exc), "data": None}

    def ListPeriods(self, name: Optional[str] = None) -> Dict[str, Any]:
        params = {"name": name} if name else None
        return self._request("GET", "/bp/period/list", params=params)

    def SearchGroups(self, period_id: str, name: str) -> Dict[str, Any]:
        return self._request("GET", "/bp/group/searchByName", params={"periodId": period_id, "name": name})

    def SearchTasks(self, group_id: str, name: str) -> Dict[str, Any]:
        return self._request("GET", "/bp/task/v2/searchByName", params={"groupId": group_id, "name": name})

    def GetGroupMarkdown(self, group_id: str) -> Dict[str, Any]:
        return self._request("GET", "/bp/group/markdown", params={"groupId": group_id})

    def ListTaskReports(self, task_id: str, page_index: int = 1, page_size: int = 10) -> Dict[str, Any]:
        """
        2.8 分页查询所有汇报（listTaskReports）

        新增可选时间过滤参数（2026-04-07 更新）：
        - businessTimeStart/End
        - relationTimeStart/End
        """
        return self._request(
            "POST",
            "/bp/task/relation/pageAllReports",
            data={"taskId": task_id, "pageIndex": page_index, "pageSize": page_size, "sortBy": "relation_time", "sortOrder": "desc"},
        )

    def ListTaskReportsWithTimeRange(
        self,
        task_id: str,
        page_index: int = 1,
        page_size: int = 10,
        business_time_start: Optional[str] = None,
        business_time_end: Optional[str] = None,
        relation_time_start: Optional[str] = None,
        relation_time_end: Optional[str] = None,
        sort_by: str = "relation_time",
        sort_order: str = "desc",
    ) -> Dict[str, Any]:
        data: Dict[str, Any] = {
            "taskId": task_id,
            "pageIndex": page_index,
            "pageSize": page_size,
            "sortBy": sort_by,
            "sortOrder": sort_order,
        }
        if business_time_start:
            data["businessTimeStart"] = business_time_start
        if business_time_end:
            data["businessTimeEnd"] = business_time_end
        if relation_time_start:
            data["relationTimeStart"] = relation_time_start
        if relation_time_end:
            data["relationTimeEnd"] = relation_time_end

        return self._request("POST", "/bp/task/relation/pageAllReports", data=data)

    def GetMonthlyReportByMonth(self, group_id: str, report_month: str) -> Dict[str, Any]:
        """
        2.23 根据分组和月份获取月度汇报（getMonthlyReportByMonth）
        GET /bp/monthly/report/getByMonth?groupId=...&reportMonth=YYYY-MM
        """
        return self._request("GET", "/bp/monthly/report/getByMonth", params={"groupId": group_id, "reportMonth": report_month})

    def GetPersonalGroupIds(self, employee_ids: List[str]) -> Dict[str, Any]:
        # 接口契约为 List<Long>。这里尽量把纯数字字符串转为 int，兼容后端严格校验类型的场景。
        payload: List[Any] = []
        for emp_id in employee_ids:
            s = str(emp_id).strip()
            if s.isdigit():
                try:
                    payload.append(int(s))
                    continue
                except Exception:
                    pass
            payload.append(s)
        return self._request("POST", "/bp/group/getPersonalGroupIds", data=payload)


def GetCurrentPeriod(client: BPClient) -> Optional[Dict[str, Any]]:
    result = client.ListPeriods()
    if result.get("resultCode") != 1:
        return None
    for period in (result.get("data") or []):
        if period.get("status") == 1:
            return period
    return None

