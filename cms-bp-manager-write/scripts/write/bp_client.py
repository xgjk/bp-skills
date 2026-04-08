#!/usr/bin/env python3
"""
BP Open API 客户端（写入更新）

约束：
- appKey 由运行时注入（依赖 cms-auth-skills），不在代码中硬编码、不回显
- 仅实现已明确 Open API 支持的写操作
"""

import json
import os
import urllib.parse
import urllib.request
from typing import Any, Dict, List, Optional, Union


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

    # ==================== 只读（用于写前确认/写后复核） ====================

    def GetGoalDetail(self, goal_id: str) -> Dict[str, Any]:
        return self._request("GET", f"/bp/goal/{goal_id}/detail")

    def GetKeyResultDetail(self, key_result_id: str) -> Dict[str, Any]:
        return self._request("GET", f"/bp/keyResult/{key_result_id}/detail")

    def GetActionDetail(self, action_id: str) -> Dict[str, Any]:
        return self._request("GET", f"/bp/action/{action_id}/detail")

    # ==================== 写入接口 ====================

    def AddKeyResult(self, goal_id: str, name: str, extra: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        payload: Dict[str, Any] = {"goalId": goal_id, "name": name}
        if extra:
            payload.update(extra)
        return self._request("POST", "/bp/task/v2/addKeyResult", data=payload)

    def AddAction(self, key_result_id: str, name: str, extra: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        payload: Dict[str, Any] = {"keyResultId": key_result_id, "name": name}
        if extra:
            payload.update(extra)
        return self._request("POST", "/bp/task/v2/addAction", data=payload)

    def AddGoal(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        return self._request("POST", "/bp/task/v2/addGoal", data=payload)

    def AlignTask(self, current_task_id: Union[str, int], upward_task_id_list: Optional[List[Union[str, int]]]) -> Dict[str, Any]:
        payload: Dict[str, Any] = {"currentTaskId": current_task_id}
        if upward_task_id_list is not None:
            payload["upwardTaskIdList"] = upward_task_id_list
        return self._request("POST", "/bp/task/v2/alignTask", data=payload)

    def UpdateTask(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        return self._request("POST", "/bp/task/v2/updateTask", data=payload)

    def SendDelayReport(self, receiver_emp_id: str, report_name: str, content: str) -> Dict[str, Any]:
        return self._request(
            "POST",
            "/bp/delayReport/send",
            data={"receiverEmpId": receiver_emp_id, "reportName": report_name, "content": content},
        )

    # ==================== 版本链（读/写） ====================

    def GetHistoryPage(self, task_id: str, page_index: int = 1, page_size: int = 10) -> Dict[str, Any]:
        return self._request(
            "GET",
            "/bp/task/v2/getHistoryPage",
            params={"taskId": task_id, "pageIndex": page_index, "pageSize": page_size},
        )

    def GetHistoryDetail(self, snapshot_id: str) -> Dict[str, Any]:
        return self._request("GET", "/bp/task/v2/getHistoryDetail", params={"id": snapshot_id})

    def Rollback(self, snapshot_id: str) -> Dict[str, Any]:
        return self._request("POST", "/bp/task/v2/rollback", data={"snapshotId": snapshot_id})

