"""
文件查看器查询端点

提供按文件扩展名查询可用查看器的功能，包含用户组访问控制过滤。
"""
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlmodel_ext import cond, rel

from middleware.auth import auth_required
from middleware.dependencies import SessionDep
from sqlmodels import (
    FileApp,
    FileAppExtension,
    FileAppGroupLink,
    FileAppSummary,
    FileViewersResponse,
    User,
    UserFileAppDefault,
)

viewers_router = APIRouter(prefix="/viewers", tags=["file", "viewers"])


@viewers_router.get(
    path='',
    summary='查询可用文件查看器',
    description='根据文件扩展名查询可用的查看器应用列表。',
)
async def get_viewers(
    session: SessionDep,
    user: Annotated[User, Depends(auth_required)],
    ext: Annotated[str, Query(max_length=20, description="文件扩展名")],
) -> FileViewersResponse:
    """
    查询可用文件查看器端点

    流程：
    1. 规范化扩展名（小写，去点号）
    2. 查询匹配的已启用应用
    3. 按用户组权限过滤
    4. 按 priority 排序
    5. 查询用户默认偏好

    认证：JWT token 必填

    错误处理：
    - 401: 未授权
    """
    # 规范化扩展名
    normalized_ext = ext.lower().strip().lstrip('.')

    # 查询匹配扩展名的应用（已启用的）
    ext_records: list[FileAppExtension] = await FileAppExtension.get(
        session,
        cond(FileAppExtension.extension == normalized_ext),
        load=rel(FileAppExtension.app),
        fetch_mode="all",
    )

    # 过滤和收集可用应用
    user_group_id = user.group_id
    viewers: list[tuple[FileAppSummary, int]] = []

    for ext_record in ext_records:
        app: FileApp = ext_record.app
        if not app.is_enabled:
            continue

        if app.is_restricted:
            group_link = await FileAppGroupLink.get(
                session,
                cond(FileAppGroupLink.app_id == app.id) &
                cond(FileAppGroupLink.group_id == user_group_id),
            )
            if not group_link:
                continue

        viewers.append((FileAppSummary.model_validate(app, from_attributes=True), ext_record.priority))

    # 按 priority 排序
    viewers.sort(key=lambda x: x[1])

    # 查询用户默认偏好
    user_default: UserFileAppDefault | None = await UserFileAppDefault.get(
        session,
        cond(UserFileAppDefault.user_id == user.id) &
        cond(UserFileAppDefault.extension == normalized_ext),
    )

    return FileViewersResponse(
        viewers=[v[0] for v in viewers],
        default_viewer_id=user_default.app_id if user_default else None,
    )
