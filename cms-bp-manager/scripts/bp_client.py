#!/usr/bin/env python3
"""
BP API 客户端封装（只读 + 审计）

基于原版 bp-manager/scripts/bp_client.py 重建，移除写入方法（归属 cms-bp-manager-write）。
增强：UTF-8 终端兼容、时间范围过滤、月度汇报查询。

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
    """兼容 LANG=en_US 等非 UTF-8 终端环境，避免中文输出/异常信息导致编码崩溃。"""
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    try:
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass


class BPClient:
    """BP API 客户端（只读 + 审计）"""

    def __init__(self, app_key: Optional[str] = None, base_url: Optional[str] = None):
        _configure_io_encoding()
        self.AppKey = app_key or os.getenv("BP_APP_KEY")
        self.BaseUrl = base_url or "https://sg-al-cwork-web.mediportal.com.cn/open-api"
        if not self.AppKey:
            raise ValueError("缺少 appKey，请通过 cms-auth-skills 注入或设置 BP_APP_KEY 环境变量")

    def _request(self, method: str, path: str, params: Optional[Dict[str, Any]] = None, data: Any = None) -> Dict[str, Any]:
        """发送 HTTP 请求"""
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

    # ==================== 周期管理 ====================

    def ListPeriods(self, name: Optional[str] = None) -> Dict[str, Any]:
        """查询周期列表"""
        params = {"name": name} if name else None
        return self._request("GET", "/bp/period/list", params=params)

    # ==================== 分组管理 ====================

    def ListGroups(self, period_id: str, only_personal: bool = False) -> Dict[str, Any]:
        """获取分组树"""
        params = {"periodId": period_id, "onlyPersonal": str(only_personal).lower()}
        return self._request("GET", "/bp/group/list", params=params)

    def GetPersonalGroupIds(self, employee_ids: List[str]) -> Dict[str, Any]:
        """批量查询员工个人类型分组 ID"""
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

    def SearchGroups(self, period_id: str, name: str) -> Dict[str, Any]:
        """按名称搜索分组"""
        return self._request("GET", "/bp/group/searchByName", params={"periodId": period_id, "name": name})

    def GetGroupMarkdown(self, group_id: str) -> Dict[str, Any]:
        """获取分组完整 BP 的 Markdown"""
        return self._request("GET", "/bp/group/markdown", params={"groupId": group_id})

    def BatchGetKeyPositionMarkdown(self, group_ids: List[str]) -> Dict[str, Any]:
        """批量获取关键岗位详情 Markdown"""
        return self._request("POST", "/bp/group/batchGetKeyPositionMarkdown", data=group_ids)

    # ==================== 任务管理 ====================

    def GetSimpleTree(self, group_id: str) -> Dict[str, Any]:
        """查询 BP 任务树（简要信息）"""
        return self._request("GET", "/bp/task/v2/getSimpleTree", params={"groupId": group_id})

    def SearchTasks(self, group_id: str, name: str) -> Dict[str, Any]:
        """按名称搜索任务"""
        return self._request("GET", "/bp/task/v2/searchByName", params={"groupId": group_id, "name": name})

    def GetTaskChildren(self, parent_id: str) -> Dict[str, Any]:
        """获取任务子树骨架"""
        return self._request("GET", "/bp/task/children", params={"parentId": parent_id})

    # ==================== 目标管理 ====================

    def ListGoals(self, group_id: str) -> Dict[str, Any]:
        """获取目标列表"""
        return self._request("GET", "/bp/goal/list", params={"groupId": group_id})

    def GetGoalDetail(self, goal_id: str) -> Dict[str, Any]:
        """获取目标详情"""
        return self._request("GET", f"/bp/goal/{goal_id}/detail")

    # ==================== 关键成果管理 ====================

    def ListKeyResults(self, goal_id: str) -> Dict[str, Any]:
        """获取关键成果列表"""
        return self._request("GET", "/bp/keyResult/list", params={"goalId": goal_id})

    def GetKeyResultDetail(self, key_result_id: str) -> Dict[str, Any]:
        """获取关键成果详情"""
        return self._request("GET", f"/bp/keyResult/{key_result_id}/detail")

    # ==================== 关键举措管理 ====================

    def ListActions(self, key_result_id: str) -> Dict[str, Any]:
        """获取关键举措列表"""
        return self._request("GET", "/bp/action/list", params={"keyResultId": key_result_id})

    def GetActionDetail(self, action_id: str) -> Dict[str, Any]:
        """获取关键举措详情"""
        return self._request("GET", f"/bp/action/{action_id}/detail")

    # ==================== 汇报管理 ====================

    def ListTaskReports(self, task_id: str, page_index: int = 1, page_size: int = 10,
                        keyword: Optional[str] = None, sort_by: str = "relation_time",
                        sort_order: str = "desc") -> Dict[str, Any]:
        """分页查询所有汇报"""
        data: Dict[str, Any] = {
            "taskId": task_id,
            "sortBy": sort_by,
            "sortOrder": sort_order,
            "pageIndex": page_index,
            "pageSize": page_size,
        }
        if keyword:
            data["keyword"] = keyword
        return self._request("POST", "/bp/task/relation/pageAllReports", data=data)

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
        """分页查询所有汇报（支持时间范围过滤）"""
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

    # ==================== 延期提醒（只读：查询历史） ====================

    def ListDelayReports(self, receiver_emp_id: str) -> Dict[str, Any]:
        """查询延期提醒汇报历史"""
        return self._request("GET", "/bp/delayReport/list", params={"receiverEmpId": receiver_emp_id})

    # ==================== 月度汇报 ====================

    def GetMonthlyReportByMonth(self, group_id: str, report_month: str) -> Dict[str, Any]:
        """根据分组和月份获取月度汇报（GET /bp/monthly/report/getByMonth）"""
        return self._request("GET", "/bp/monthly/report/getByMonth", params={"groupId": group_id, "reportMonth": report_month})


# ==================== 便捷函数 ====================

def GetCurrentPeriod(client: BPClient) -> Optional[Dict[str, Any]]:
    """获取当前启用的周期"""
    result = client.ListPeriods()
    if result.get("resultCode") != 1:
        return None
    for period in (result.get("data") or []):
        if period.get("status") == 1:
            return period
    return None


def FindMyGroup(client: BPClient, period_id: str, employee_id: str) -> Optional[str]:
    """找到员工在指定周期下的个人分组 ID"""
    result = client.GetPersonalGroupIds([employee_id])
    if result.get("resultCode") != 1:
        return None
    data = result.get("data") or {}
    group_id = data.get(employee_id)
    if not group_id:
        try:
            group_id = data.get(int(employee_id))
        except Exception:
            group_id = None
    return group_id


if __name__ == "__main__":
    client = BPClient()
    print("测试周期列表:")
    result = client.ListPeriods()
    print(json.dumps(result, indent=2, ensure_ascii=False))
