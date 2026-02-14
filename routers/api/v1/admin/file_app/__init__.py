"""
管理员文件应用管理端点

提供文件查看器应用的 CRUD、扩展名管理和用户组权限管理。
"""
from uuid import UUID

from fastapi import APIRouter, Depends, status
from loguru import logger as l
from sqlalchemy import select

from middleware.auth import admin_required
from middleware.dependencies import SessionDep, TableViewRequestDep
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
)
from utils import http_exceptions

admin_file_app_router = APIRouter(
    prefix="/file-app",
    tags=["admin", "file_app"],
    dependencies=[Depends(admin_required)],
)


@admin_file_app_router.get(
    path='/list',
    summary='列出所有文件应用',
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
        group_links_result = await session.exec(
            select(FileAppGroupLink).where(FileAppGroupLink.app_id == app.id)
        )
        group_links: list[FileAppGroupLink] = list(group_links_result.all())
        apps.append(FileAppResponse.from_app(app, extensions, group_links))

    return FileAppListResponse(apps=apps, total=result.count)


@admin_file_app_router.post(
    path='/',
    summary='创建文件应用',
    status_code=status.HTTP_201_CREATED,
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

    l.info(f"创建文件应用: {app.name} ({app.app_key})")

    return FileAppResponse.from_app(app, extensions, group_links)


@admin_file_app_router.get(
    path='/{app_id}',
    summary='获取文件应用详情',
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
    app: FileApp | None = await FileApp.get(session, FileApp.id == app_id)
    if not app:
        http_exceptions.raise_not_found("应用不存在")

    extensions = await FileAppExtension.get(
        session,
        FileAppExtension.app_id == app.id,
        fetch_mode="all",
    )
    group_links_result = await session.exec(
        select(FileAppGroupLink).where(FileAppGroupLink.app_id == app.id)
    )
    group_links: list[FileAppGroupLink] = list(group_links_result.all())

    return FileAppResponse.from_app(app, extensions, group_links)


@admin_file_app_router.patch(
    path='/{app_id}',
    summary='更新文件应用',
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
    app: FileApp | None = await FileApp.get(session, FileApp.id == app_id)
    if not app:
        http_exceptions.raise_not_found("应用不存在")

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
        FileAppExtension.app_id == app.id,
        fetch_mode="all",
    )
    group_links_result = await session.exec(
        select(FileAppGroupLink).where(FileAppGroupLink.app_id == app.id)
    )
    group_links: list[FileAppGroupLink] = list(group_links_result.all())

    l.info(f"更新文件应用: {app.name} ({app.app_key})")

    return FileAppResponse.from_app(app, extensions, group_links)


@admin_file_app_router.delete(
    path='/{app_id}',
    summary='删除文件应用',
    status_code=status.HTTP_204_NO_CONTENT,
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
    app: FileApp | None = await FileApp.get(session, FileApp.id == app_id)
    if not app:
        http_exceptions.raise_not_found("应用不存在")

    app_name = app.app_key
    await FileApp.delete(session, app)
    l.info(f"删除文件应用: {app_name}")


@admin_file_app_router.put(
    path='/{app_id}/extensions',
    summary='全量替换扩展名列表',
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
    app: FileApp | None = await FileApp.get(session, FileApp.id == app_id)
    if not app:
        http_exceptions.raise_not_found("应用不存在")

    # 删除旧的扩展名
    old_extensions: list[FileAppExtension] = await FileAppExtension.get(
        session,
        FileAppExtension.app_id == app_id,
        fetch_mode="all",
    )
    for old_ext in old_extensions:
        await FileAppExtension.delete(session, old_ext, commit=False)

    # 创建新的扩展名
    new_extensions: list[FileAppExtension] = []
    for i, ext in enumerate(request.extensions):
        normalized = ext.lower().strip().lstrip('.')
        ext_record = FileAppExtension(
            app_id=app_id,
            extension=normalized,
            priority=i,
        )
        session.add(ext_record)
        new_extensions.append(ext_record)

    await session.commit()
    # refresh 新创建的记录
    for ext_record in new_extensions:
        await session.refresh(ext_record)

    group_links_result = await session.exec(
        select(FileAppGroupLink).where(FileAppGroupLink.app_id == app_id)
    )
    group_links: list[FileAppGroupLink] = list(group_links_result.all())

    l.info(f"更新文件应用 {app.app_key} 的扩展名: {request.extensions}")

    return FileAppResponse.from_app(app, new_extensions, group_links)


@admin_file_app_router.put(
    path='/{app_id}/groups',
    summary='全量替换允许的用户组',
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
    app: FileApp | None = await FileApp.get(session, FileApp.id == app_id)
    if not app:
        http_exceptions.raise_not_found("应用不存在")

    # 删除旧的用户组关联
    old_links_result = await session.exec(
        select(FileAppGroupLink).where(FileAppGroupLink.app_id == app_id)
    )
    old_links: list[FileAppGroupLink] = list(old_links_result.all())
    for old_link in old_links:
        await session.delete(old_link)

    # 创建新的用户组关联
    new_links: list[FileAppGroupLink] = []
    for group_id in request.group_ids:
        link = FileAppGroupLink(app_id=app_id, group_id=group_id)
        session.add(link)
        new_links.append(link)

    await session.commit()

    extensions = await FileAppExtension.get(
        session,
        FileAppExtension.app_id == app_id,
        fetch_mode="all",
    )

    l.info(f"更新文件应用 {app.app_key} 的用户组权限: {request.group_ids}")

    return FileAppResponse.from_app(app, extensions, new_links)
