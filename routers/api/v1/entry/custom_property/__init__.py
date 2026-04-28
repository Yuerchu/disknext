"""
用户自定义属性定义路由

提供自定义属性模板的增删改查功能。
用户可以定义类型化的属性模板（如标签、评分、分类等），
然后通过元数据 PATCH 端点为对象设置属性值。

路由前缀：/custom_property
"""
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends
from loguru import logger as l

from middleware.auth import auth_required
from middleware.scope import require_scope
from middleware.dependencies import SessionDep
from sqlmodels import (
    CustomPropertyDefinition,
    CustomPropertyCreateRequest,
    CustomPropertyUpdateRequest,
    CustomPropertyResponse,
    User,
)
from utils import http_exceptions
from utils.http.error_codes import ErrorCode as E

router = APIRouter(
    prefix="/custom_property",
    tags=["custom_property"],
)


@router.get(
    path='',
    summary='获取自定义属性定义列表',
    description='获取当前用户的所有自定义属性定义，按 sort_order 排序。',
    dependencies=[Depends(require_scope("files:read:own"))],
)
async def router_list_custom_properties(
    session: SessionDep,
    user: Annotated[User, Depends(auth_required)],
) -> list[CustomPropertyResponse]:
    """
    获取自定义属性定义列表端点

    认证：JWT token 必填

    返回当前用户定义的所有自定义属性模板。
    """
    definitions = await CustomPropertyDefinition.get(
        session,
        CustomPropertyDefinition.owner_id == user.id,
        fetch_mode="all",
    )

    return [
        CustomPropertyResponse(
            id=d.id,
            name=d.name,
            type=d.type,
            icon=d.icon,
            options=d.options,
            default_value=d.default_value,
            sort_order=d.sort_order,
        )
        for d in sorted(definitions, key=lambda x: x.sort_order)
    ]


@router.post(
    path='',
    summary='创建自定义属性定义',
    description='创建一个新的自定义属性模板。',
    status_code=204,
    dependencies=[Depends(require_scope("files:create:own"))],
)
async def router_create_custom_property(
    session: SessionDep,
    user: Annotated[User, Depends(auth_required)],
    request: CustomPropertyCreateRequest,
) -> None:
    """
    创建自定义属性定义端点

    认证：JWT token 必填

    错误处理：
    - 400: 请求数据无效
    - 409: 同名属性已存在
    """
    # 检查同名属性
    existing = await CustomPropertyDefinition.get(
        session,
        (CustomPropertyDefinition.owner_id == user.id) &
        (CustomPropertyDefinition.name == request.name),
    )
    if existing:
        http_exceptions.raise_conflict(E.ENTRY_CUSTOM_PROP_DUPLICATE, "同名自定义属性已存在")

    definition = CustomPropertyDefinition(
        owner_id=user.id,
        name=request.name,
        type=request.type,
        icon=request.icon,
        options=request.options,
        default_value=request.default_value,
    )
    definition = await definition.save(session)

    l.info(f"用户 {user.id} 创建了自定义属性: {request.name}")


@router.patch(
    path='/{id}',
    summary='更新自定义属性定义',
    description='更新自定义属性模板的名称、图标、选项等。',
    status_code=204,
    dependencies=[Depends(require_scope("files:write:own"))],
)
async def router_update_custom_property(
    session: SessionDep,
    user: Annotated[User, Depends(auth_required)],
    id: UUID,
    request: CustomPropertyUpdateRequest,
) -> None:
    """
    更新自定义属性定义端点

    认证：JWT token 必填

    错误处理：
    - 404: 属性定义不存在
    - 403: 无权操作此属性
    """
    definition = await CustomPropertyDefinition.get_exist_one(session, id)

    if definition.owner_id != user.id:
        http_exceptions.raise_forbidden(E.ENTRY_CUSTOM_PROP_FORBIDDEN, "无权操作此属性")

    definition = await definition.update(session, request)

    l.info(f"用户 {user.id} 更新了自定义属性: {id}")


@router.delete(
    path='/{id}',
    summary='删除自定义属性定义',
    description='删除自定义属性模板。注意：不会自动清理已使用该属性的元数据条目。',
    status_code=204,
    dependencies=[Depends(require_scope("files:delete:own"))],
)
async def router_delete_custom_property(
    session: SessionDep,
    user: Annotated[User, Depends(auth_required)],
    id: UUID,
) -> None:
    """
    删除自定义属性定义端点

    认证：JWT token 必填

    错误处理：
    - 404: 属性定义不存在
    - 403: 无权操作此属性
    """
    definition = await CustomPropertyDefinition.get_exist_one(session, id)

    if definition.owner_id != user.id:
        http_exceptions.raise_forbidden(E.ENTRY_CUSTOM_PROP_FORBIDDEN, "无权操作此属性")

    _ = await CustomPropertyDefinition.delete(session, instances=definition)

    l.info(f"用户 {user.id} 删除了自定义属性: {id}")
