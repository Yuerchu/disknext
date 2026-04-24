"""
管理员文件应用管理端点

提供文件查看器应用的 CRUD、扩展名管理、用户组权限管理和 WOPI Discovery。
"""
from uuid import UUID

import aiohttp
from fastapi import APIRouter, Depends, status
from loguru import logger as l
from sqlmodel_ext import cond

from middleware.scope import require_scope
from middleware.dependencies import SessionDep, TableViewRequestDep
from utils.wopi import parse_wopi_discovery_xml
from sqlmodels import (
    FileApp,
    FileAppCreateRequest,
    FileAppExtension,
    FileAppGroupLink,
    FileAppListResponse,
    FileAppResponse,
    FileAppUpdateRequest,
    ExtensionUpdateRequest,
    GroupAccessUpdateRequest,
    WopiDiscoveredExtension,
    WopiDiscoveryResponse,
)
from sqlmodels.file_app import FileAppType
from utils import http_exceptions

admin_file_app_router = APIRouter(
    prefix="/file_app",
    tags=["admin", "file_app"],
)


@admin_file_app_router.get(
    path='/',
    summary='列出所有文件应用',
    dependencies=[Depends(require_scope("admin.file_apps:read:all"))],
)
async def list_file_apps(
    session: SessionDep,
    table_view: TableViewRequestDep,
) -> FileAppListResponse:
    """
    列出所有文件应用端点（分页）

    认证：管理员权限
    """
    result = await FileApp.get_with_count(
        session,
        table_view=table_view,
    )

    apps: list[FileAppResponse] = []
    for app in result.items:
        extensions = await FileAppExtension.get(
            session,
            FileAppExtension.app_id == app.id,
            fetch_mode="all",
        )
        group_links = await FileAppGroupLink.get(
            session,
            cond(FileAppGroupLink.app_id == app.id),
            fetch_mode="all",
        )
        apps.append(FileAppResponse.model_validate(
            app, from_attributes=True,
            update={
                'extensions': [ext.extension for ext in extensions],
                'allowed_group_ids': [link.group_id for link in group_links],
            },
        ))

    return FileAppListResponse(apps=apps, total=result.count)


@admin_file_app_router.post(
    path='/',
    summary='创建文件应用',
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_scope("admin.file_apps:create:all"))],
)
async def create_file_app(
    session: SessionDep,
    request: FileAppCreateRequest,
) -> FileAppResponse:
    """
    创建文件应用端点

    认证：管理员权限

    错误处理：
    - 409: app_key 已存在
    """
    # 检查 app_key 唯一
    existing = await FileApp.get(session, FileApp.app_key == request.app_key)
    if existing:
        http_exceptions.raise_conflict(f"应用标识 '{request.app_key}' 已存在")

    # 创建应用
    app = FileApp(
        name=request.name,
        app_key=request.app_key,
        type=request.type,
        icon=request.icon,
        description=request.description,
        is_enabled=request.is_enabled,
        is_restricted=request.is_restricted,
        iframe_url_template=request.iframe_url_template,
        wopi_discovery_url=request.wopi_discovery_url,
        wopi_editor_url_template=request.wopi_editor_url_template,
    )
    app = await app.save(session)
    app_id = app.id

    # 创建扩展名关联
    extensions: list[FileAppExtension] = []
    for i, ext in enumerate(request.extensions):
        normalized = ext.lower().strip().lstrip('.')
        ext_record = FileAppExtension(
            app_id=app_id,
            extension=normalized,
            priority=i,
        )
        ext_record = await ext_record.save(session)
        extensions.append(ext_record)

    # 创建用户组关联
    group_links: list[FileAppGroupLink] = []
    for group_id in request.allowed_group_ids:
        link = FileAppGroupLink(app_id=app_id, group_id=group_id)
        session.add(link)
        group_links.append(link)
    if group_links:
        await session.commit()
        await session.refresh(app)

    l.info(f"创建文件应用: {app.name} ({app.app_key})")

    return FileAppResponse.model_validate(
            app, from_attributes=True,
            update={
                'extensions': [ext.extension for ext in extensions],
                'allowed_group_ids': [link.group_id for link in group_links],
            },
        )


@admin_file_app_router.get(
    path='/{app_id}',
    summary='获取文件应用详情',
    dependencies=[Depends(require_scope("admin.file_apps:read:all"))],
)
async def get_file_app(
    session: SessionDep,
    app_id: UUID,
) -> FileAppResponse:
    """
    获取文件应用详情端点

    认证：管理员权限

    错误处理：
    - 404: 应用不存在
    """
    app = await FileApp.get_exist_one(session, app_id)

    extensions = await FileAppExtension.get(
        session,
        FileAppExtension.app_id == app.id,
        fetch_mode="all",
    )
    group_links = await FileAppGroupLink.get(
        session,
        cond(FileAppGroupLink.app_id == app.id),
        fetch_mode="all",
    )

    return FileAppResponse.model_validate(
            app, from_attributes=True,
            update={
                'extensions': [ext.extension for ext in extensions],
                'allowed_group_ids': [link.group_id for link in group_links],
            },
        )


@admin_file_app_router.patch(
    path='/{app_id}',
    summary='更新文件应用',
    dependencies=[Depends(require_scope("admin.file_apps:write:all"))],
)
async def update_file_app(
    session: SessionDep,
    app_id: UUID,
    request: FileAppUpdateRequest,
) -> FileAppResponse:
    """
    更新文件应用端点

    认证：管理员权限

    错误处理：
    - 404: 应用不存在
    - 409: 新 app_key 已被其他应用使用
    """
    app = await FileApp.get_exist_one(session, app_id)

    # 检查 app_key 唯一性
    if request.app_key is not None and request.app_key != app.app_key:
        existing = await FileApp.get(session, FileApp.app_key == request.app_key)
        if existing:
            http_exceptions.raise_conflict(f"应用标识 '{request.app_key}' 已存在")

    # 更新非 None 字段
    update_data = request.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(app, key, value)

    app = await app.save(session)

    extensions = await FileAppExtension.get(
        session,
        cond(FileAppExtension.app_id == app.id),
        fetch_mode="all",
    )
    group_links = await FileAppGroupLink.get(
        session,
        cond(FileAppGroupLink.app_id == app.id),
        fetch_mode="all",
    )

    l.info(f"更新文件应用: {app.name} ({app.app_key})")

    return FileAppResponse.model_validate(
            app, from_attributes=True,
            update={
                'extensions': [ext.extension for ext in extensions],
                'allowed_group_ids': [link.group_id for link in group_links],
            },
        )


@admin_file_app_router.delete(
    path='/{app_id}',
    summary='删除文件应用',
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(require_scope("admin.file_apps:delete:all"))],
)
async def delete_file_app(
    session: SessionDep,
    app_id: UUID,
) -> None:
    """
    删除文件应用端点（级联删除扩展名、用户偏好和用户组关联）

    认证：管理员权限

    错误处理：
    - 404: 应用不存在
    """
    app = await FileApp.get_exist_one(session, app_id)

    app_name = app.app_key
    _ = await FileApp.delete(session, app)
    l.info(f"删除文件应用: {app_name}")


@admin_file_app_router.put(
    path='/{app_id}/extensions',
    summary='全量替换扩展名列表',
    dependencies=[Depends(require_scope("admin.file_apps:write:all"))],
)
async def update_extensions(
    session: SessionDep,
    app_id: UUID,
    request: ExtensionUpdateRequest,
) -> FileAppResponse:
    """
    全量替换扩展名列表端点

    先删除旧的扩展名关联，再创建新的。

    认证：管理员权限

    错误处理：
    - 404: 应用不存在
    """
    app = await FileApp.get_exist_one(session, app_id)

    # 保留旧扩展名的 wopi_action_url（Discovery 填充的值）
    old_extensions: list[FileAppExtension] = await FileAppExtension.get(
        session,
        FileAppExtension.app_id == app_id,
        fetch_mode="all",
    )
    old_url_map: dict[str, str] = {
        ext.extension: ext.wopi_action_url
        for ext in old_extensions
        if ext.wopi_action_url
    }
    for old_ext in old_extensions:
        _ = await FileAppExtension.delete(session, old_ext, commit=False)
    await session.flush()

    # 创建新的扩展名（保留已有的 wopi_action_url）
    new_extensions: list[FileAppExtension] = []
    for i, ext in enumerate(request.extensions):
        normalized = ext.lower().strip().lstrip('.')
        ext_record = FileAppExtension(
            app_id=app_id,
            extension=normalized,
            priority=i,
            wopi_action_url=old_url_map.get(normalized),
        )
        session.add(ext_record)
        new_extensions.append(ext_record)

    await session.commit()
    # refresh commit 后过期的对象
    await session.refresh(app)
    for ext_record in new_extensions:
        await session.refresh(ext_record)

    group_links = await FileAppGroupLink.get(
        session,
        cond(FileAppGroupLink.app_id == app_id),
        fetch_mode="all",
    )

    l.info(f"更新文件应用 {app.app_key} 的扩展名: {request.extensions}")

    return FileAppResponse.model_validate(
        app, from_attributes=True,
        update={
            'extensions': [ext.extension for ext in new_extensions],
            'allowed_group_ids': [link.group_id for link in group_links],
        },
    )


@admin_file_app_router.put(
    path='/{app_id}/groups',
    summary='全量替换允许的用户组',
    dependencies=[Depends(require_scope("admin.file_apps:write:all"))],
)
async def update_group_access(
    session: SessionDep,
    app_id: UUID,
    request: GroupAccessUpdateRequest,
) -> FileAppResponse:
    """
    全量替换允许的用户组端点

    先删除旧的关联，再创建新的。

    认证：管理员权限

    错误处理：
    - 404: 应用不存在
    """
    app = await FileApp.get_exist_one(session, app_id)

    # 删除旧的用户组关联
    old_links = await FileAppGroupLink.get(
        session,
        cond(FileAppGroupLink.app_id == app_id),
        fetch_mode="all",
    )
    for old_link in old_links:
        await session.delete(old_link)

    # 创建新的用户组关联
    new_links: list[FileAppGroupLink] = []
    for group_id in request.group_ids:
        link = FileAppGroupLink(app_id=app_id, group_id=group_id)
        session.add(link)
        new_links.append(link)

    await session.commit()
    await session.refresh(app)

    extensions = await FileAppExtension.get(
        session,
        FileAppExtension.app_id == app_id,
        fetch_mode="all",
    )

    l.info(f"更新文件应用 {app.app_key} 的用户组权限: {request.group_ids}")

    return FileAppResponse.model_validate(
        app, from_attributes=True,
        update={
            'extensions': [ext.extension for ext in extensions],
            'allowed_group_ids': [link.group_id for link in new_links],
        },
    )


@admin_file_app_router.post(
    path='/{app_id}/discover',
    summary='执行 WOPI Discovery',
    dependencies=[Depends(require_scope("admin.file_apps:write:all"))],
)
async def discover_wopi(
    session: SessionDep,
    app_id: UUID,
) -> WopiDiscoveryResponse:
    """
    从 WOPI 服务端获取 Discovery XML 并自动配置扩展名和 URL 模板。

    流程：
    1. 验证 FileApp 存在且为 WOPI 类型
    2. 使用 FileApp.wopi_discovery_url 获取 Discovery XML
    3. 解析 XML，提取扩展名和动作 URL
    4. 全量替换 FileAppExtension 记录（带 wopi_action_url）

    认证：管理员权限

    错误处理：
    - 404: 应用不存在
    - 400: 非 WOPI 类型 / discovery URL 未配置 / XML 解析失败
    - 502: WOPI 服务端不可达或返回无效响应
    """
    app = await FileApp.get_exist_one(session, app_id)

    if app.type != FileAppType.WOPI:
        http_exceptions.raise_bad_request("仅 WOPI 类型应用支持自动发现")

    if not app.wopi_discovery_url:
        http_exceptions.raise_bad_request("未配置 WOPI Discovery URL")

    # commit 后对象会过期，先保存需要的值
    discovery_url = app.wopi_discovery_url
    app_key = app.app_key

    # 获取 Discovery XML
    try:
        async with aiohttp.ClientSession() as client:
            async with client.get(
                discovery_url,
                timeout=aiohttp.ClientTimeout(total=15),
            ) as resp:
                if resp.status != 200:
                    http_exceptions.raise_bad_gateway(
                        f"WOPI 服务端返回 HTTP {resp.status}"
                    )
                xml_content = await resp.text()
    except aiohttp.ClientError as e:
        http_exceptions.raise_bad_gateway(f"无法连接 WOPI 服务端: {e}")

    # 解析 XML
    try:
        action_urls, app_names = parse_wopi_discovery_xml(xml_content)
    except ValueError as e:
        http_exceptions.raise_bad_request(str(e))

    if not action_urls:
        return WopiDiscoveryResponse(app_names=app_names)

    # 全量替换扩展名
    old_extensions = await FileAppExtension.get(
        session,
        cond(FileAppExtension.app_id == app_id),
        fetch_mode="all",
    )
    for old_ext in old_extensions:
        _ = await FileAppExtension.delete(session, old_ext, commit=False)
    await session.flush()

    new_extensions: list[FileAppExtension] = []
    discovered: list[WopiDiscoveredExtension] = []
    for i, (ext, action_url) in enumerate(sorted(action_urls.items())):
        ext_record = FileAppExtension(
            app_id=app_id,
            extension=ext,
            priority=i,
            wopi_action_url=action_url,
        )
        session.add(ext_record)
        new_extensions.append(ext_record)
        discovered.append(WopiDiscoveredExtension(extension=ext, action_url=action_url))

    await session.commit()

    l.info(
        f"WOPI Discovery 完成: 应用 {app_key}, "
        f"发现 {len(discovered)} 个扩展名"
    )

    return WopiDiscoveryResponse(
        discovered_extensions=discovered,
        app_names=app_names,
        applied_count=len(discovered),
    )
