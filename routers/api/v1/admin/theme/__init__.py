from uuid import UUID

from fastapi import APIRouter, Depends, status
from loguru import logger as l
from sqlalchemy import update as sql_update

from middleware.auth import admin_required
from middleware.dependencies import SessionDep
from sqlmodels import (
    ThemePreset,
    ThemePresetCreateRequest,
    ThemePresetUpdateRequest,
    ThemePresetResponse,
    ThemePresetListResponse,
)
from utils import http_exceptions

admin_theme_router = APIRouter(
    prefix="/theme",
    tags=["admin", "admin_theme"],
    dependencies=[Depends(admin_required)],
)


@admin_theme_router.get(
    path='/',
    summary='获取主题预设列表',
)
async def router_admin_theme_list(session: SessionDep) -> ThemePresetListResponse:
    """
    获取所有主题预设列表

    认证：需要管理员权限

    响应：
    - ThemePresetListResponse: 包含所有主题预设的列表
    """
    presets: list[ThemePreset] = await ThemePreset.get(session, fetch_mode="all")
    return ThemePresetListResponse(
        themes=[ThemePresetResponse.from_preset(p) for p in presets]
    )


@admin_theme_router.post(
    path='/',
    summary='创建主题预设',
    status_code=status.HTTP_204_NO_CONTENT,
)
async def router_admin_theme_create(
        session: SessionDep,
        request: ThemePresetCreateRequest,
) -> None:
    """
    创建新的主题预设

    认证：需要管理员权限

    请求体：
    - name: 预设名称（唯一）
    - colors: 颜色配置对象

    错误处理：
    - 409: 名称已存在
    """
    # 检查名称唯一性
    existing = await ThemePreset.get(session, ThemePreset.name == request.name)
    if existing:
        http_exceptions.raise_conflict(f"主题预设名称 '{request.name}' 已存在")

    preset = ThemePreset(
        name=request.name,
        **request.colors.model_dump(),
    )
    await preset.save(session)
    l.info(f"管理员创建了主题预设: {request.name}")


@admin_theme_router.patch(
    path='/{preset_id}',
    summary='更新主题预设',
    status_code=status.HTTP_204_NO_CONTENT,
)
async def router_admin_theme_update(
        session: SessionDep,
        preset_id: UUID,
        request: ThemePresetUpdateRequest,
) -> None:
    """
    部分更新主题预设

    认证：需要管理员权限

    路径参数：
    - preset_id: 预设UUID

    请求体（均可选）：
    - name: 预设名称
    - colors: 颜色配置对象

    错误处理：
    - 404: 预设不存在
    - 409: 名称已被其他预设使用
    """
    preset: ThemePreset | None = await ThemePreset.get(
        session, ThemePreset.id == preset_id
    )
    if not preset:
        http_exceptions.raise_not_found("主题预设不存在")

    # 检查名称唯一性（排除自身）
    if request.name is not None and request.name != preset.name:
        existing = await ThemePreset.get(session, ThemePreset.name == request.name)
        if existing:
            http_exceptions.raise_conflict(f"主题预设名称 '{request.name}' 已存在")
        preset.name = request.name

    # 更新颜色字段
    if request.colors is not None:
        color_data = request.colors.model_dump()
        for key, value in color_data.items():
            setattr(preset, key, value)

    await preset.save(session)
    l.info(f"管理员更新了主题预设: {preset.name}")


@admin_theme_router.delete(
    path='/{preset_id}',
    summary='删除主题预设',
    status_code=status.HTTP_204_NO_CONTENT,
)
async def router_admin_theme_delete(
        session: SessionDep,
        preset_id: UUID,
) -> None:
    """
    删除主题预设

    认证：需要管理员权限

    路径参数：
    - preset_id: 预设UUID

    错误处理：
    - 404: 预设不存在

    副作用：
    - 关联用户的 theme_preset_id 会被数据库 SET NULL
    """
    preset: ThemePreset | None = await ThemePreset.get(
        session, ThemePreset.id == preset_id
    )
    if not preset:
        http_exceptions.raise_not_found("主题预设不存在")

    await preset.delete(session)
    l.info(f"管理员删除了主题预设: {preset.name}")


@admin_theme_router.patch(
    path='/{preset_id}/default',
    summary='设为默认主题预设',
    status_code=status.HTTP_204_NO_CONTENT,
)
async def router_admin_theme_set_default(
        session: SessionDep,
        preset_id: UUID,
) -> None:
    """
    将指定预设设为默认主题

    认证：需要管理员权限

    路径参数：
    - preset_id: 预设UUID

    错误处理：
    - 404: 预设不存在

    逻辑：
    - 事务中先清除所有旧默认，再设新默认
    """
    preset: ThemePreset | None = await ThemePreset.get(
        session, ThemePreset.id == preset_id
    )
    if not preset:
        http_exceptions.raise_not_found("主题预设不存在")

    # 清除所有旧默认
    await session.execute(
        sql_update(ThemePreset)
        .where(ThemePreset.is_default == True)  # noqa: E712
        .values(is_default=False)
    )

    # 设新默认
    preset.is_default = True
    await preset.save(session)
    l.info(f"管理员将主题预设 '{preset.name}' 设为默认")
