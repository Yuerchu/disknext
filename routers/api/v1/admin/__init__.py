from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, status
from loguru import logger as l

from middleware.dependencies import SessionDep, ServerConfigDep
from middleware.scope import require_scope
from sqlmodels import (
    User, ResponseBase,
    Entry, EntryType, Share, AdminSummaryResponse, MetricsSummary, LicenseInfo, VersionInfo,
    Aria2TestRequest
)
from sqlmodel_ext import SQLModelBase
from sqlmodels.server_config import ServerConfig, ServerConfigUpdateRequest
from utils import http_exceptions
from utils.conf import appmeta

from .file import admin_file_router
from .file_app import admin_file_app_router
from .group import admin_group_router
from .policy import admin_policy_router
from .share import admin_share_router
from .task import admin_task_router
from .user import admin_user_router
from .theme import admin_theme_router

# 管理员根目录 /api/admin
admin_router = APIRouter(
    prefix="/admin",
    tags=["admin"],
)

admin_router.include_router(admin_group_router)
admin_router.include_router(admin_user_router)
admin_router.include_router(admin_file_router)
admin_router.include_router(admin_file_app_router)
admin_router.include_router(admin_policy_router)
admin_router.include_router(admin_share_router)
admin_router.include_router(admin_task_router)
admin_router.include_router(admin_theme_router)

# 离线下载 /api/admin/aria2
admin_aria2_router = APIRouter(
    prefix='/admin/aria2',
    tags=['admin', 'admin_aria2']
)

@admin_router.get(
    path='/',
    summary='自己是否为管理员',
    dependencies=[Depends(require_scope("admin.dashboard:read:all"))],
    status_code=status.HTTP_204_NO_CONTENT
)
async def is_admin() -> None:
    """
    检查当前用户是否具有管理员权限。

    如果用户是管理员，则返回 204 No Content 响应；否则返回 403 Forbidden 错误。

    Returns:
        None: 无内容响应
    """
    return None

@admin_router.get(
    path='/summary',
    summary='获取站点概况',
    description='Get site summary information',
    dependencies=[Depends(require_scope("admin.dashboard:read:all"))],
)
async def router_admin_get_summary(
    session: SessionDep,
    config: ServerConfigDep,
) -> AdminSummaryResponse:
    """
    获取站点概况信息，包括用户数、分享数、文件数等统计指标。

    响应数据结构：
    - metrics_summary: 统计摘要（日期列表、每日增量、总计）
    - site_urls: 站点URL列表
    - license: 许可证信息（过期时间、签发时间、域名配置）
    - version: 版本信息（版本号、是否Pro、提交哈希）

    Returns:
        AdminSummaryResponse: 包含站点概况信息的响应模型。
    """
    # 统计最近 14 天的数据
    days_count = 14
    now = datetime.now()
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)

    dates: list[datetime] = []
    files: list[int] = []
    users: list[int] = []
    shares: list[int] = []

    # 从 11 天前到今天
    for i in range(days_count - 1, -1, -1):
        day_start = today_start - timedelta(days=i)
        day_end = day_start + timedelta(days=1)
        dates.append(day_start)

        # 统计每日新增
        file_count = await Entry.count(
            session,
            Entry.type == EntryType.FILE,
            created_after_datetime=day_start,
            created_before_datetime=day_end,
        )
        user_count = await User.count(
            session,
            created_after_datetime=day_start,
            created_before_datetime=day_end,
        )
        share_count = await Share.count(
            session,
            created_after_datetime=day_start,
            created_before_datetime=day_end,
        )

        files.append(file_count)
        users.append(user_count)
        shares.append(share_count)

    # 统计总数
    file_total = await Entry.count(session, Entry.type == EntryType.FILE)
    user_total = await User.count(session)
    share_total = await Share.count(session)
    entities_total = await Entry.count(session)

    metrics_summary = MetricsSummary(
        dates=dates,
        files=files,
        users=users,
        shares=shares,
        file_total=file_total,
        user_total=user_total,
        share_total=share_total,
        entities_total=entities_total,
        generated_at=now,
    )

    # 获取站点 URL
    site_urls: list[str] = []
    if config.site_url:
        site_urls.append(config.site_url)

    # 许可证信息（Pro 版本从缓存读取，CE 版本永不过期）
    _payload = get_cached_license() if get_cached_license else None
    if _payload and not _payload.is_expired():
        license_info = LicenseInfo(
            expired_at=_payload.expires_at,
            signed_at=_payload.issued_at,
            root_domains=[],
            domains=[_payload.domain],
            vol_domains=[],
        )
    else:
        license_info = LicenseInfo(
            expired_at=datetime.max,
            signed_at=now,
            root_domains=[],
            domains=[],
            vol_domains=[],
        )

    # 版本信息
    version_info = VersionInfo(
        version=appmeta.BackendVersion,
        pro=_payload is not None and not _payload.is_expired(),
        commit="dev",
    )

    return AdminSummaryResponse(
        metrics_summary=metrics_summary,
        site_urls=site_urls,
        license=license_info,
        version=version_info,
    )

@admin_router.get(
    path='/news',
    summary='获取社区新闻',
    description='Get community news',
    dependencies=[Depends(require_scope("admin.dashboard:read:all"))],
)
def router_admin_get_news() -> ResponseBase:
    """
    获取社区新闻信息，包括最新的动态和公告。
    
    Returns:
        ResponseBase: 包含社区新闻信息的响应模型。
    """
    http_exceptions.raise_not_implemented()

@admin_router.patch(
    path='/settings',
    summary='更新设置',
    dependencies=[Depends(require_scope("admin.settings:write:all"))],
    status_code=204,
)
async def router_admin_update_settings(
    session: SessionDep,
    config: ServerConfigDep,
    request: ServerConfigUpdateRequest,
) -> None:
    """
    更新服务器配置。

    :param session: 数据库会话
    :param config: 当前服务器配置
    :param request: 更新请求（仅包含需要修改的字段）
    """
    from utils.redis.server_config_cache import ServerConfigCache
    config = await config.update(session, request)
    await ServerConfigCache.invalidate()
    l.info("管理员更新了服务器配置")


@admin_router.get(
    path='/settings',
    summary='获取设置',
    dependencies=[Depends(require_scope("admin.settings:read:all"))],
)
async def router_admin_get_settings(
    config: ServerConfigDep,
) -> ServerConfig:
    """
    获取服务器配置。
    """
    return config

@admin_aria2_router.post(
    path='/test',
    summary='测试 Aria2 连接',
    description='Test Aria2 RPC connection',
    dependencies=[Depends(require_scope("admin.settings:write:all"))],
    status_code=204,
)
async def router_admin_aira2_test(
    request: Aria2TestRequest,
) -> None:
    """
    测试 Aria2 RPC 连接。

    :param request: 测试请求
    :raises HTTPException: 连接失败时抛出 400
    """
    import aiohttp

    try:
        payload = {
            "jsonrpc": "2.0",
            "id": "test",
            "method": "aria2.getVersion",
            "params": [f"token:{request.secret}"] if request.secret else [],
        }

        async with aiohttp.ClientSession() as client:
            async with client.post(request.rpc_url, json=payload, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                if resp.status != 200:
                    raise HTTPException(
                        status_code=400,
                        detail=f"连接失败，HTTP {resp.status}",
                    )

                result = await resp.json()
                if "error" in result:
                    raise HTTPException(
                        status_code=400,
                        detail=f"Aria2 错误: {result['error']['message']}",
                    )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"连接失败: {str(e)}")