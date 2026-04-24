"""
FastAPI 依赖注入

包含 HTTP 端点的通用依赖：
- SessionDep: 数据库会话依赖
- TimeFilterRequestDep: 时间筛选查询依赖（用于 count 等统计接口）
- TableViewRequestDep: 分页排序查询依赖（包含时间筛选 + 分页排序）
- UserFilterParamsDep: 用户筛选参数依赖（用于管理员用户列表）
- require_captcha: 验证码校验依赖注入工厂
"""
from collections.abc import Awaitable, Callable
from typing import Annotated, TypeAlias
from uuid import UUID

from fastapi import Depends, Form, Query
from sqlmodel.ext.asyncio.session import AsyncSession
from sqlmodel_ext import TimeFilterRequest, TableViewRequest

from sqlmodels.database_connection import DatabaseManager
from sqlmodels.server_config import ServerConfig
from sqlmodels.user import UserFilterParams, UserStatus
from sqlmodels.captcha import CaptchaScene, verify_captcha_if_needed


# --- 数据库会话依赖 ---

SessionDep: TypeAlias = Annotated[AsyncSession, Depends(DatabaseManager.get_session)]
"""数据库会话依赖，用于路由函数中获取数据库会话"""


# --- 服务器配置依赖 ---

async def _get_server_config(session: SessionDep) -> ServerConfig:
    """获取服务器配置（ID 固定为 1）"""
    return await ServerConfig.get_instance(session)


ServerConfigDep: TypeAlias = Annotated[ServerConfig, Depends(_get_server_config)]
"""服务器配置依赖，用于路由函数中获取全局配置"""


# --- 时间筛选依赖 ---

TimeFilterRequestDep: TypeAlias = Annotated[TimeFilterRequest, Depends()]
"""获取时间筛选参数的依赖（用于 count 等统计接口）"""


# --- 分页排序依赖 ---

TableViewRequestDep: TypeAlias = Annotated[TableViewRequest, Depends()]
"""获取分页排序和时间筛选参数的依赖"""


# --- 用户筛选依赖 ---

async def _get_user_filter_params(
    group_id: Annotated[UUID | None, Query()] = None,
    email_contains: Annotated[str | None, Query(max_length=255)] = None,
    nickname_contains: Annotated[str | None, Query(max_length=255)] = None,
    status: Annotated[UserStatus | None, Query()] = None,
) -> UserFilterParams:
    """解析用户筛选查询参数"""
    return UserFilterParams(
        group_id=group_id,
        email_contains=email_contains,
        nickname_contains=nickname_contains,
        status=status,
    )


UserFilterParamsDep: TypeAlias = Annotated[UserFilterParams, Depends(_get_user_filter_params)]
"""用户筛选参数依赖（用于管理员用户列表）"""


# --- 验证码校验依赖 ---

def require_captcha(scene: CaptchaScene) -> Callable[..., Awaitable[None]]:
    """
    验证码校验依赖注入工厂。

    根据场景查询数据库设置，判断是否需要验证码。
    需要则校验前端提交的 captcha_code，失败则抛出异常。

    使用方式::

        @router.post('/session', dependencies=[Depends(require_captcha(CaptchaScene.LOGIN))])
        async def login(...): ...

    :param scene: 验证码使用场景（LOGIN / REGISTER / FORGET）
    """
    async def _verify_captcha(
            config: ServerConfigDep,
            captcha_code: Annotated[str | None, Form()] = None,
    ) -> None:
        await verify_captcha_if_needed(config, scene, captcha_code)

    return _verify_captcha
