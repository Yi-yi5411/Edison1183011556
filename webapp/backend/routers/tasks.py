# -*- coding: utf-8 -*-
"""并行任务中心路由：启动、查询、停止检测项并行评定。"""
from typing import List

from fastapi import APIRouter
from pydantic import BaseModel

from deps import ApiError, ok
from task_runner import get_task_runner

router = APIRouter(tags=["tasks"])


class StartTasksBody(BaseModel):
    sheet_keys: List[str] = []
    title: str = ""


@router.get("/tasks")
def list_tasks(limit: int = 12):
    """最近的并行任务（新的在前）。"""
    return ok({"items": get_task_runner().list(limit)}, "任务列表读取成功")


@router.get("/tasks/{task_id}")
def get_task(task_id: str):
    task = get_task_runner().get(task_id)
    if not task:
        raise ApiError("任务不存在", 404)
    return ok(task, "任务读取成功")


@router.post("/tasks/assess")
def start_assess_tasks(body: StartTasksBody):
    """把已勾选检测项拆成并行评定任务；只读快照，全部完成后统一写回工程。"""
    try:
        task = get_task_runner().start_assessment(body.sheet_keys, body.title)
    except RuntimeError as exc:
        raise ApiError(str(exc), 409)
    return ok(task, "并行任务已启动")


@router.post("/tasks/{task_id}/cancel")
def cancel_task(task_id: str):
    task = get_task_runner().cancel(task_id)
    if not task:
        raise ApiError("任务不存在", 404)
    return ok(task, "停止请求已提交")
