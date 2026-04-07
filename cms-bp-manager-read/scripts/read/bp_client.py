#!/usr/bin/env python3
"""
BP Open API 客户端（只读）

约束：
- 仅封装只读接口
- appKey 由运行时注入（依赖 cms-auth-skills），不在代码中硬编码、不回显
"""

import json
import os
import urllib.parse
import urllib.request
from typing import Any, Dict, List, Optional


class BPClient:
    def __init__(self, app_key: Optional[str] = None, base_url: Optional[str] = None):
        self.AppKey = app_key or os.getenv("BP_APP_KEY")
        self.BaseUrl = base_url or "https://sg-al-cwork-web.mediportal.com.cn/open-api"
        if not self.AppKey:
            raise ValueError("缺少 appKey，请通过 cms-auth-skills 注入或设置 BP_APP_KEY")

    def _request(self, method: str, path: str, params: Optional[Dict[str, Any]] = None, data: Any = None) -> Dict[str, Any]:
        url = f"{self.BaseUrl}{path}"
        headers = {"appKey": self.AppKey, "Content-Type": "application/json"}
        if params:
            url = f"{url}?{urllib.parse.urlencode(params)}"

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
        return self._request(
            "POST",
            "/bp/task/relation/pageAllReports",
            data={"taskId": task_id, "pageIndex": page_index, "pageSize": page_size, "sortBy": "relation_time", "sortOrder": "desc"},
        )

    def GetPersonalGroupIds(self, employee_ids: List[str]) -> Dict[str, Any]:
        return self._request("POST", "/bp/group/getPersonalGroupIds", data=employee_ids)


def GetCurrentPeriod(client: BPClient) -> Optional[Dict[str, Any]]:
    result = client.ListPeriods()
    if result.get("resultCode") != 1:
        return None
    for period in (result.get("data") or []):
        if period.get("status") == 1:
            return period
    return None

