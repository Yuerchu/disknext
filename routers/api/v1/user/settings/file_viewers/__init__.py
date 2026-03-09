"""
用户文件查看器偏好设置端点

提供用户"始终使用"默认查看器的增删查功能。
"""
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, status
from sqlalchemy import and_

from middleware.auth import auth_required
from middleware.dependencies import SessionDep
from sqlmodels import (
    FileApp,
    FileAppExtension,
    SetDefaultViewerRequest,
    User,
    UserFileAppDefault,
    UserFileAppDefaultResponse,
)
from utils import http_exceptions

file_viewers_router = APIRouter(
    prefix='/file-viewers',
    tags=["user", "user_settings", "file_viewers"],
    dependencies=[Depends(auth_required)],
)


@file_viewers_router.put(
    path='/default',
    summary='设置默认查看器',
    description='为指定扩展名设置"始终使用"的查看器。',
)
async def set_default_viewer(
    session: SessionDep,
    user: Annotated[User, Depends(auth_required)],
    request: SetDefaultViewerRequest,
) -> UserFileAppDefaultResponse:
    """
    设置默认查看器端点

    如果用户已有该扩展名的默认设置，则更新；否则创建新记录。

    认证：JWT token 必填

    错误处理：
    - 404: 应用不存在
    - 400: 应用不支持该扩展名
    """
    # 规范化扩展名
    normalized_ext = request.extension.lower().strip().lstrip('.')

    # 验证应用存在
    app: FileApp | None = await FileApp.get(session, FileApp.id == request.app_id)
    if not app:
        http_exceptions.raise_not_found("应用不存在")

    # 验证应用支持该扩展名
    ext_record: FileAppExtension | None = await FileAppExtension.get(
        session,
        and_(
            FileAppExtension.app_id == app.id,
            FileAppExtension.extension == normalized_ext,
        ),
    )
    if not ext_record:
        http_exceptions.raise_bad_request("该应用不支持此扩展名")

    # 查找已有记录
    existing: UserFileAppDefault | None = await UserFileAppDefault.get(
        session,
        and_(
            UserFileAppDefault.user_id == user.id,
            UserFileAppDefault.extension == normalized_ext,
        ),
    )

    if existing:
        existing.app_id = request.app_id
        existing = await existing.save(session, load=UserFileAppDefault.app)
        return existing.to_response()
    else:
        new_default = UserFileAppDefault(
            user_id=user.id,
            extension=normalized_ext,
            app_id=request.app_id,
        )
        new_default = await new_default.save(session, load=UserFileAppDefault.app)
        return new_default.to_response()


@file_viewers_router.get(
    path='/defaults',
    summary='列出所有默认查看器设置',
    description='获取当前用户所有"始终使用"的查看器偏好。',
)
async def list_default_viewers(
    session: SessionDep,
    user: Annotated[User, Depends(auth_required)],
) -> list[UserFileAppDefaultResponse]:
    """
    列出所有默认查看器设置端点

    认证：JWT token 必填
    """
    defaults: list[UserFileAppDefault] = await UserFileAppDefault.get(
        session,
        UserFileAppDefault.user_id == user.id,
        fetch_mode="all",
        load=UserFileAppDefault.app,
    )
    return [d.to_response() for d in defaults]


@file_viewers_router.delete(
    path='/default/{default_id}',
    summary='撤销默认查看器设置',
    description='删除指定的"始终使用"偏好。',
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_default_viewer(
    session: SessionDep,
    user: Annotated[User, Depends(auth_required)],
    default_id: UUID,
) -> None:
    """
    撤销默认查看器设置端点

    认证：JWT token 必填

    错误处理：
    - 404: 记录不存在或不属于当前用户
    """
    existing: UserFileAppDefault | None = await UserFileAppDefault.get(
        session,
        and_(
            UserFileAppDefault.id == default_id,
            UserFileAppDefault.user_id == user.id,
        ),
    )
    if not existing:
        http_exceptions.raise_not_found("默认设置不存在")

    await UserFileAppDefault.delete(session, existing)
