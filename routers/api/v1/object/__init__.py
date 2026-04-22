"""
对象操作路由

提供文件和目录对象的管理功能：删除、移动、复制、重命名等。

路由前缀：/object
"""
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from loguru import logger as l

from middleware.auth import auth_required
from middleware.dependencies import SessionDep
from sqlmodels import (
    CreateFileRequest,
    Group,
    Entry,
    EntryCopyRequest,
    EntryDeleteRequest,
    EntryMoveRequest,
    EntryPropertyDetailResponse,
    EntryPropertyResponse,
    EntryUpdateRequest,
    EntrySwitchPolicyRequest,
    EntryType,
    PhysicalFile,
    Policy,
    PolicyType,
    Task,
    TaskProps,
    TaskStatus,
    TaskSummaryBase,
    TaskType,
    User,
    # 元数据相关
    EntryMetadata,
    MetadataResponse,
    MetadataPatchRequest,
    INTERNAL_NAMESPACES,
    USER_WRITABLE_NAMESPACES,
)
from utils.storage import create_storage_driver, migrate_file_with_task, migrate_directory_files
from sqlmodels.database_connection import DatabaseManager
from utils import http_exceptions

from .custom_property import router as custom_property_router

object_router = APIRouter(
    prefix="/object",
    tags=["object"]
)
object_router.include_router(custom_property_router)

@object_router.post(
    path='/',
    summary='创建空白文件',
    description='在指定目录下创建空白文件。',
    status_code=204,
)
async def router_object_create(
    session: SessionDep,
    user: Annotated[User, Depends(auth_required)],
    request: CreateFileRequest,
) -> None:
    """
    创建空白文件端点

    :param session: 数据库会话
    :param user: 当前登录用户
    :param request: 创建文件请求（parent_id, name）
    :return: 创建结果
    """
    user_id = user.id

    # 验证文件名
    if not request.name or '/' in request.name or '\\' in request.name:
        raise HTTPException(status_code=400, detail="无效的文件名")

    # 验证父目录（排除已删除的）
    parent = await Entry.get(
        session,
        (Entry.id == request.parent_id) & (Entry.deleted_at == None)
    )
    if not parent or parent.owner_id != user_id:
        raise HTTPException(status_code=404, detail="父目录不存在")

    if not parent.is_folder:
        raise HTTPException(status_code=400, detail="父对象不是目录")

    if parent.is_banned:
        http_exceptions.raise_banned("目标目录已被封禁，无法执行此操作")

    # 检查是否已存在同名文件（仅检查未删除的）
    existing = await Entry.get(
        session,
        (Entry.owner_id == user_id) &
        (Entry.parent_id == parent.id) &
        (Entry.name == request.name) &
        (Entry.deleted_at == None)
    )
    if existing:
        raise HTTPException(status_code=409, detail="同名文件已存在")

    # 确定存储策略
    policy_id = request.policy_id or parent.policy_id
    policy = await Policy.get_exist_one(session, policy_id)

    parent_id = parent.id

    # 生成存储路径并创建空文件
    driver = create_storage_driver(policy)
    _dir_path, _storage_name, storage_path = await driver.generate_path(
        user_id=user_id,
        original_filename=request.name,
    )
    await driver.create_empty(storage_path)

    # 创建 PhysicalFile 记录
    physical_file = PhysicalFile(
        storage_path=storage_path,
        size=0,
        policy_id=policy_id,
        reference_count=1,
    )
    physical_file = await physical_file.save(session)

    # 创建 Entry 记录
    file_object = Entry(
        name=request.name,
        type=EntryType.FILE,
        size=0,
        physical_file_id=physical_file.id,
        parent_id=parent_id,
        owner_id=user_id,
        policy_id=policy_id,
    )
    file_object = await file_object.save(session)

    l.info(f"创建空白文件: {request.name}")


@object_router.delete(
    path='/',
    summary='删除对象',
    description='删除一个或多个对象（文件或目录），文件会移动到用户回收站。',
    status_code=204,
)
async def router_object_delete(
    session: SessionDep,
    user: Annotated[User, Depends(auth_required)],
    request: EntryDeleteRequest,
) -> None:
    """
    删除对象端点（软删除到回收站）

    流程：
    1. 验证对象存在且属于当前用户
    2. 设置 deleted_at 时间戳
    3. 保存原 parent_id 到 deleted_original_parent_id
    4. 将 parent_id 置 NULL 脱离文件树
    5. 子对象和物理文件不做任何变更

    :param session: 数据库会话
    :param user: 当前登录用户
    :param request: 删除请求（包含待删除对象的UUID列表）
    :return: 删除结果
    """
    user_id = user.id
    objects_to_delete: list[Entry] = []

    for obj_id in request.ids:
        obj = await Entry.get(
            session,
            (Entry.id == obj_id) & (Entry.deleted_at == None)
        )
        if not obj or obj.owner_id != user_id:
            continue

        # 不能删除根目录
        if obj.parent_id is None:
            l.warning(f"尝试删除根目录被阻止: {obj.name}")
            continue

        objects_to_delete.append(obj)

    if objects_to_delete:
        deleted_count = await Entry.soft_delete_batch(session, objects_to_delete)
        l.info(f"用户 {user_id} 软删除了 {deleted_count} 个对象到回收站")


@object_router.patch(
    path='/',
    summary='移动对象',
    description='移动一个或多个对象到目标目录',
    status_code=204,
)
async def router_object_move(
    session: SessionDep,
    user: Annotated[User, Depends(auth_required)],
    request: EntryMoveRequest,
) -> None:
    """
    移动对象端点

    :param session: 数据库会话
    :param user: 当前登录用户
    :param request: 移动请求（包含源对象UUID列表和目标目录UUID）
    :return: 移动结果
    """
    # 存储 user.id，避免后续 save() 导致 user 过期后无法访问
    user_id = user.id

    # 验证目标目录（排除已删除的）
    dst = await Entry.get(
        session,
        (Entry.id == request.dst_id) & (Entry.deleted_at == None)
    )
    if not dst or dst.owner_id != user_id:
        raise HTTPException(status_code=404, detail="目标目录不存在")

    if not dst.is_folder:
        raise HTTPException(status_code=400, detail="目标不是有效文件夹")

    if dst.is_banned:
        http_exceptions.raise_banned("目标目录已被封禁，无法执行此操作")

    # 存储 dst 的属性，避免后续数据库操作导致 dst 过期后无法访问
    dst_id = dst.id
    dst_parent_id = dst.parent_id

    moved_count = 0

    for src_id in request.src_ids:
        src = await Entry.get(
            session,
            (Entry.id == src_id) & (Entry.deleted_at == None)
        )
        if not src or src.owner_id != user_id:
            continue

        if src.is_banned:
            continue

        # 不能移动根目录
        if src.parent_id is None:
            continue

        # 检查是否移动到自身或子目录（防止循环引用）
        if src.id == dst_id:
            continue

        # 检查是否将目录移动到其子目录中（循环检测）
        if src.is_folder:
            current_parent_id = dst_parent_id
            is_cycle = False
            while current_parent_id:
                if current_parent_id == src.id:
                    is_cycle = True
                    break
                current = await Entry.get(session, Entry.id == current_parent_id)
                current_parent_id = current.parent_id if current else None
            if is_cycle:
                continue

        # 检查目标目录下是否存在同名对象（仅检查未删除的）
        existing = await Entry.get(
            session,
            (Entry.owner_id == user_id) &
            (Entry.parent_id == dst_id) &
            (Entry.name == src.name) &
            (Entry.deleted_at == None)
        )
        if existing:
            continue  # 跳过重名对象

        src.parent_id = dst_id
        await src.save(session, commit=False, refresh=False)
        moved_count += 1

    # 统一提交所有更改
    await session.commit()


@object_router.post(
    path='/copies',
    summary='复制对象',
    description='复制一个或多个对象到目标目录。文件复制仅增加物理文件引用计数，不复制物理文件。',
    status_code=204,
)
async def router_object_copy(
    session: SessionDep,
    user: Annotated[User, Depends(auth_required)],
    request: EntryCopyRequest,
) -> None:
    """
    复制对象端点

    流程：
    1. 验证目标目录存在且属于当前用户
    2. 对于每个源对象：
       - 验证源对象存在且属于当前用户
       - 检查目标目录下是否存在同名对象
       - 如果是文件：增加 PhysicalFile 引用计数，创建新 Entry
       - 如果是目录：递归复制所有子对象
    3. 返回复制结果

    :param session: 数据库会话
    :param user: 当前登录用户
    :param request: 复制请求
    :return: 复制结果
    """
    # 存储 user.id，避免后续 save() 导致 user 过期后无法访问
    user_id = user.id

    # 验证目标目录（排除已删除的）
    dst = await Entry.get(
        session,
        (Entry.id == request.dst_id) & (Entry.deleted_at == None)
    )
    if not dst or dst.owner_id != user_id:
        raise HTTPException(status_code=404, detail="目标目录不存在")

    if not dst.is_folder:
        raise HTTPException(status_code=400, detail="目标不是有效文件夹")

    if dst.is_banned:
        http_exceptions.raise_banned("目标目录已被封禁，无法执行此操作")

    copied_count = 0
    new_ids: list[UUID] = []
    total_copied_size = 0

    for src_id in request.src_ids:
        src = await Entry.get(
            session,
            (Entry.id == src_id) & (Entry.deleted_at == None)
        )
        if not src or src.owner_id != user_id:
            continue

        if src.is_banned:
            http_exceptions.raise_banned("源对象已被封禁，无法执行此操作")

        # 不能复制根目录
        if src.parent_id is None:
            http_exceptions.raise_banned("无法复制根目录")

        # 不能复制到自身
        # [TODO] 视为创建副本
        if src.id == dst.id:
            continue

        # 不能将目录复制到其子目录中
        if src.is_folder:
            current = dst
            is_cycle = False
            while current and current.parent_id:
                if current.parent_id == src.id:
                    is_cycle = True
                    break
                current = await Entry.get(session, Entry.id == current.parent_id)
            if is_cycle:
                continue

        # 检查目标目录下是否存在同名对象（仅检查未删除的）
        existing = await Entry.get(
            session,
            (Entry.owner_id == user_id) &
            (Entry.parent_id == dst.id) &
            (Entry.name == src.name) &
            (Entry.deleted_at == None)
        )
        if existing:
            # [TODO] 应当询问用户是否覆盖、跳过或创建副本
            continue

        # 递归复制
        count, ids, copied_size = await src.copy_recursive(session, dst.id, user_id)
        copied_count += count
        new_ids.extend(ids)
        total_copied_size += copied_size

    # 更新用户存储配额
    if total_copied_size > 0:
        await user.adjust_storage(session, total_copied_size)

    l.info(f"用户 {user_id} 复制了 {copied_count} 个对象")


@object_router.patch(
    path='/{object_id}',
    summary='更新对象',
    description='更新对象属性（如重命名）。',
    status_code=204,
)
async def router_object_update(
    session: SessionDep,
    user: Annotated[User, Depends(auth_required)],
    object_id: UUID,
    request: EntryUpdateRequest,
) -> None:
    """
    更新对象端点（重命名等部分更新）

    流程：
    1. 验证对象存在且属于当前用户
    2. 验证新名称格式（不含非法字符）
    3. 检查同目录下是否存在同名对象
    4. 更新 name 字段
    5. 返回更新结果

    :param session: 数据库会话
    :param user: 当前登录用户
    :param object_id: 对象UUID（路径参数）
    :param request: 更新请求
    :return: 更新结果
    """
    # 存储 user.id，避免后续 save() 导致 user 过期后无法访问
    user_id = user.id

    # 验证对象存在（排除已删除的）
    obj = await Entry.get(
        session,
        (Entry.id == object_id) & (Entry.deleted_at == None)
    )
    if not obj:
        raise HTTPException(status_code=404, detail="对象不存在")

    if obj.owner_id != user_id:
        raise HTTPException(status_code=403, detail="无权操作此对象")

    if obj.is_banned:
        http_exceptions.raise_banned()

    # 不能重命名根目录
    if obj.parent_id is None:
        raise HTTPException(status_code=400, detail="无法重命名根目录")

    if request.name is not None:
        # 验证新名称格式
        new_name = request.name.strip()
        if not new_name:
            raise HTTPException(status_code=400, detail="名称不能为空")

        if '/' in new_name or '\\' in new_name:
            raise HTTPException(status_code=400, detail="名称不能包含斜杠")

        # 如果名称没有变化，直接返回
        if obj.name == new_name:
            return  # noqa: already 204

        # 检查同目录下是否存在同名对象（仅检查未删除的）
        existing = await Entry.get(
            session,
            (Entry.owner_id == user_id) &
            (Entry.parent_id == obj.parent_id) &
            (Entry.name == new_name) &
            (Entry.deleted_at == None)
        )
        if existing:
            raise HTTPException(status_code=409, detail="同名对象已存在")

        # 更新名称
        obj.name = new_name
        obj = await obj.save(session)

        l.info(f"用户 {user_id} 将对象 {obj.id} 重命名为 {new_name}")


@object_router.get(
    path='/{object_id}',
    summary='获取对象基本属性',
    description='获取对象的基本属性信息（名称、类型、大小、创建/修改时间等）。',
)
async def router_object_property(
    session: SessionDep,
    user: Annotated[User, Depends(auth_required)],
    object_id: UUID,
) -> EntryPropertyResponse:
    """
    获取对象基本属性端点

    :param session: 数据库会话
    :param user: 当前登录用户
    :param object_id: 对象UUID
    :return: 对象基本属性
    """
    obj = await Entry.get(
        session,
        (Entry.id == object_id) & (Entry.deleted_at == None)
    )
    if not obj:
        raise HTTPException(status_code=404, detail="对象不存在")

    if obj.owner_id != user.id:
        raise HTTPException(status_code=403, detail="无权查看此对象")

    return EntryPropertyResponse(
        id=obj.id,
        name=obj.name,
        type=obj.type,
        size=obj.size,
        mime_type=obj.mime_type,
        created_at=obj.created_at,
        updated_at=obj.updated_at,
        parent_id=obj.parent_id,
    )


@object_router.get(
    path='/{object_id}/detail',
    summary='获取对象详细属性',
    description='获取对象的详细属性信息，包括元数据、分享统计、存储信息等。',
)
async def router_object_property_detail(
    session: SessionDep,
    user: Annotated[User, Depends(auth_required)],
    object_id: UUID,
) -> EntryPropertyDetailResponse:
    """
    获取对象详细属性端点

    :param session: 数据库会话
    :param user: 当前登录用户
    :param object_id: 对象UUID
    :return: 对象详细属性
    """
    obj = await Entry.get(
        session,
        (Entry.id == object_id) & (Entry.deleted_at == None),
        load=Entry.metadata_entries,
    )
    if not obj:
        raise HTTPException(status_code=404, detail="对象不存在")

    if obj.owner_id != user.id:
        raise HTTPException(status_code=403, detail="无权查看此对象")

    # 获取策略名称
    policy = await Policy.get(session, Policy.id == obj.policy_id)
    policy_name = policy.name if policy else None

    # 获取分享统计
    from sqlmodels import Share
    shares = await Share.get(
        session,
        Share.object_id == obj.id,
        fetch_mode="all"
    )
    share_count = len(shares)
    total_views = sum(s.views for s in shares)
    total_downloads = sum(s.downloads for s in shares)

    # 获取物理文件信息（引用计数、校验和）
    reference_count = 1
    checksum_md5: str | None = None
    checksum_sha256: str | None = None
    if obj.physical_file_id:
        physical_file = await PhysicalFile.get(session, PhysicalFile.id == obj.physical_file_id)
        if physical_file:
            reference_count = physical_file.reference_count
            checksum_md5 = physical_file.checksum_md5
            checksum_sha256 = physical_file.checksum_sha256

    # 构建元数据字典（排除内部命名空间）
    metadata: dict[str, str] = {}
    for entry in obj.metadata_entries:
        ns = entry.name.split(":")[0] if ":" in entry.name else ""
        if ns not in INTERNAL_NAMESPACES:
            metadata[entry.name] = entry.value

    return EntryPropertyDetailResponse(
        id=obj.id,
        name=obj.name,
        type=obj.type,
        size=obj.size,
        mime_type=obj.mime_type,
        created_at=obj.created_at,
        updated_at=obj.updated_at,
        parent_id=obj.parent_id,
        checksum_md5=checksum_md5,
        checksum_sha256=checksum_sha256,
        policy_name=policy_name,
        share_count=share_count,
        total_views=total_views,
        total_downloads=total_downloads,
        reference_count=reference_count,
        metadatas=metadata,
    )


@object_router.patch(
    path='/{object_id}/policy',
    summary='切换对象存储策略',
)
async def router_object_switch_policy(
    session: SessionDep,
    background_tasks: BackgroundTasks,
    user: Annotated[User, Depends(auth_required)],
    object_id: UUID,
    request: EntrySwitchPolicyRequest,
) -> TaskSummaryBase:
    """
    切换对象的存储策略

    文件：立即创建后台迁移任务，将文件从源策略搬到目标策略。
    目录：更新目录 policy_id（新文件使用新策略）；
          若 is_migrate_existing=True，额外创建后台任务迁移所有已有文件。

    认证：JWT Bearer Token

    错误处理：
    - 404: 对象不存在
    - 403: 无权操作此对象 / 用户组无权使用目标策略
    - 400: 目标策略与当前相同 / 不能对根目录操作
    """
    user_id = user.id

    # 查找对象
    obj = await Entry.get(
        session,
        (Entry.id == object_id) & (Entry.deleted_at == None)
    )
    if not obj:
        http_exceptions.raise_not_found("对象不存在")
    if obj.owner_id != user_id:
        http_exceptions.raise_forbidden("无权操作此对象")
    if obj.is_banned:
        http_exceptions.raise_banned()

    # 根目录不能直接切换策略（应通过子对象或子目录操作）
    if obj.parent_id is None:
        raise HTTPException(status_code=400, detail="不能对根目录切换存储策略，请对子目录操作")

    # 校验目标策略存在
    dest_policy = await Policy.get(session, Policy.id == request.policy_id)
    if not dest_policy:
        http_exceptions.raise_not_found("目标存储策略不存在")

    # 校验用户组权限
    group: Group = await user.awaitable_attrs.group
    await session.refresh(group, ['policies'])
    allowed_ids = {p.id for p in group.policies}
    if request.policy_id not in allowed_ids:
        http_exceptions.raise_forbidden("当前用户组无权使用该存储策略")

    # 不能切换到相同策略
    if obj.policy_id == request.policy_id:
        raise HTTPException(status_code=400, detail="目标策略与当前策略相同")

    # 保存必要的属性，避免 save 后对象过期
    src_policy_id = obj.policy_id
    obj_id = obj.id
    obj_is_file = obj.type == EntryType.FILE
    dest_policy_id = request.policy_id
    dest_policy_name = dest_policy.name

    # 创建任务记录
    task = Task(
        type=TaskType.POLICY_MIGRATE,
        status=TaskStatus.QUEUED,
        user_id=user_id,
    )
    task = await task.save(session)
    task_id = task.id

    task_props = TaskProps(
        task_id=task_id,
        source_policy_id=src_policy_id,
        dest_policy_id=dest_policy_id,
        object_id=obj_id,
    )
    task_props = await task_props.save(session)

    if obj_is_file:
        # 文件：后台迁移
        async def _run_file_migration() -> None:
            async with DatabaseManager.session() as bg_session:
                bg_obj = await Entry.get(bg_session, Entry.id == obj_id)
                bg_policy = await Policy.get(bg_session, Policy.id == dest_policy_id)
                bg_task = await Task.get(bg_session, Task.id == task_id)
                await migrate_file_with_task(bg_session, bg_obj, bg_policy, bg_task)

        background_tasks.add_task(_run_file_migration)
    else:
        # 目录：先更新目录自身的 policy_id
        obj = await Entry.get(session, Entry.id == obj_id)
        obj.policy_id = dest_policy_id
        obj = await obj.save(session)

        if request.is_migrate_existing:
            # 后台迁移所有已有文件
            async def _run_dir_migration() -> None:
                async with DatabaseManager.session() as bg_session:
                    bg_folder = await Entry.get(bg_session, Entry.id == obj_id)
                    bg_policy = await Policy.get(bg_session, Policy.id == dest_policy_id)
                    bg_task = await Task.get(bg_session, Task.id == task_id)
                    await migrate_directory_files(bg_session, bg_folder, bg_policy, bg_task)

            background_tasks.add_task(_run_dir_migration)
        else:
            # 不迁移已有文件，直接完成任务
            task = await Task.get(session, Task.id == task_id)
            task.status = TaskStatus.COMPLETED
            task.progress = 100
            task = await task.save(session)

    # 重新获取 task 以读取最新状态
    task = await Task.get(session, Task.id == task_id)

    l.info(f"用户 {user_id} 请求切换对象 {obj_id} 存储策略 → {dest_policy_name}")

    return TaskSummaryBase(
        id=task.id,
        type=task.type,
        status=task.status,
        progress=task.progress,
        error=task.error,
        user_id=task.user_id,
        created_at=task.created_at,
        updated_at=task.updated_at,
    )


# ==================== 元数据端点 ====================

@object_router.get(
    path='/{object_id}/metadata',
    summary='获取对象元数据',
    description='获取对象的元数据键值对，可按命名空间过滤。',
)
async def router_get_object_metadata(
    session: SessionDep,
    user: Annotated[User, Depends(auth_required)],
    object_id: UUID,
    ns: str | None = None,
) -> MetadataResponse:
    """
    获取对象元数据端点

    认证：JWT token 必填

    查询参数：
    - ns: 逗号分隔的命名空间列表（如 exif,stream），不传返回所有非内部命名空间

    错误处理：
    - 404: 对象不存在
    - 403: 无权查看此对象
    """
    obj = await Entry.get(
        session,
        (Entry.id == object_id) & (Entry.deleted_at == None),
        load=Entry.metadata_entries,
    )
    if not obj:
        raise HTTPException(status_code=404, detail="对象不存在")

    if obj.owner_id != user.id:
        raise HTTPException(status_code=403, detail="无权查看此对象")

    # 解析命名空间过滤
    ns_filter: set[str] | None = None
    if ns:
        ns_filter = {n.strip() for n in ns.split(",") if n.strip()}
        # 不允许查看内部命名空间
        ns_filter -= INTERNAL_NAMESPACES

    # 构建元数据字典
    metadata: dict[str, str] = {}
    for entry in obj.metadata_entries:
        entry_ns = entry.name.split(":")[0] if ":" in entry.name else ""
        if entry_ns in INTERNAL_NAMESPACES:
            continue
        if ns_filter is not None and entry_ns not in ns_filter:
            continue
        metadata[entry.name] = entry.value

    return MetadataResponse(metadatas=metadata)


@object_router.patch(
    path='/{object_id}/metadata',
    summary='批量更新对象元数据',
    description='批量设置或删除对象的元数据条目。仅允许修改 custom: 命名空间。',
    status_code=204,
)
async def router_patch_object_metadata(
    session: SessionDep,
    user: Annotated[User, Depends(auth_required)],
    object_id: UUID,
    request: MetadataPatchRequest,
) -> None:
    """
    批量更新对象元数据端点

    请求体中值为 None 的键将被删除，其余键将被设置/更新。
    用户只能修改 custom: 命名空间的条目。

    认证：JWT token 必填

    错误处理：
    - 400: 尝试修改非 custom: 命名空间的条目
    - 404: 对象不存在
    - 403: 无权操作此对象
    """
    obj = await Entry.get(
        session,
        (Entry.id == object_id) & (Entry.deleted_at == None),
    )
    if not obj:
        raise HTTPException(status_code=404, detail="对象不存在")

    if obj.owner_id != user.id:
        raise HTTPException(status_code=403, detail="无权操作此对象")

    for patch in request.patches:
        # 验证命名空间
        patch_ns = patch.key.split(":")[0] if ":" in patch.key else ""
        if patch_ns not in USER_WRITABLE_NAMESPACES:
            raise HTTPException(
                status_code=400,
                detail=f"不允许修改命名空间 '{patch_ns}' 的元数据，仅允许 custom: 命名空间",
            )

        if patch.value is None:
            # 删除元数据条目
            existing = await EntryMetadata.get(
                session,
                (EntryMetadata.object_id == object_id) & (EntryMetadata.name == patch.key),
            )
            if existing:
                await EntryMetadata.delete(session, instances=existing)
        else:
            # 设置/更新元数据条目
            existing = await EntryMetadata.get(
                session,
                (EntryMetadata.object_id == object_id) & (EntryMetadata.name == patch.key),
            )
            if existing:
                existing.value = patch.value
                existing = await existing.save(session)
            else:
                entry = EntryMetadata(
                    object_id=object_id,
                    name=patch.key,
                    value=patch.value,
                    is_public=True,
                )
                entry = await entry.save(session)

    l.info(f"用户 {user.id} 更新了对象 {object_id} 的 {len(request.patches)} 条元数据")
