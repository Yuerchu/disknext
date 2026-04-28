"""
对象操作路由

提供文件和目录对象的管理功能：删除、移动、复制、重命名等。

路由前缀：/object
"""
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, Depends
from loguru import logger as l
from sqlmodel import col

from middleware.auth import auth_required
from middleware.scope import require_scope
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
from utils.http.error_codes import ErrorCode as E

from .custom_property import router as custom_property_router

entry_router = APIRouter(
    prefix="/object",
    tags=["object"]
)
entry_router.include_router(custom_property_router)

@entry_router.post(
    path='/',
    summary='创建空白文件',
    description='在指定目录下创建空白文件。',
    status_code=204,
    dependencies=[Depends(require_scope("files:create:own"))],
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
        http_exceptions.raise_bad_request(E.ENTRY_INVALID_NAME, "无效的文件名")

    # 验证父目录（排除已删除的）
    parent = await Entry.get(
        session,
        (Entry.id == request.parent_id) & (Entry.deleted_at == None)
    )
    if not parent or parent.owner_id != user_id:
        http_exceptions.raise_not_found(E.ENTRY_PARENT_NOT_FOUND, "父目录不存在")

    if not parent.type == EntryType.FOLDER:
        http_exceptions.raise_bad_request(E.ENTRY_PARENT_NOT_DIR, "父对象不是目录")

    if parent.is_banned:
        http_exceptions.raise_banned(E.ENTRY_TARGET_BANNED, "目标目录已被封禁，无法执行此操作")

    # 检查是否已存在同名文件（仅检查未删除的）
    existing = await Entry.get(
        session,
        (Entry.owner_id == user_id) &
        (Entry.parent_id == parent.id) &
        (Entry.name == request.name) &
        (Entry.deleted_at == None)
    )
    if existing:
        http_exceptions.raise_conflict(E.ENTRY_DUPLICATE, "同名文件已存在")

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


@entry_router.delete(
    path='/',
    summary='删除对象',
    description='删除一个或多个对象（文件或目录），文件会移动到用户回收站。',
    status_code=204,
    dependencies=[Depends(require_scope("files:delete:own"))],
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

    # 批量查询所有待删除对象（单次 SQL）
    all_entries = await Entry.get(
        session,
        col(Entry.id).in_(request.ids) & (Entry.deleted_at == None),
        fetch_mode="all",
    )
    objects_to_delete = [
        obj for obj in all_entries
        if obj.owner_id == user_id and obj.parent_id is not None
    ]
    # 记录被阻止的根目录删除尝试
    for obj in all_entries:
        if obj.owner_id == user_id and obj.parent_id is None:
            l.warning(f"尝试删除根目录被阻止: {obj.name}")

    if objects_to_delete:
        deleted_count = await Entry.soft_delete_batch(session, objects_to_delete)
        l.info(f"用户 {user_id} 软删除了 {deleted_count} 个对象到回收站")


@entry_router.patch(
    path='/',
    summary='移动对象',
    description='移动一个或多个对象到目标目录',
    status_code=204,
    dependencies=[Depends(require_scope("files:write:own"))],
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
        http_exceptions.raise_not_found(E.ENTRY_TARGET_NOT_FOUND, "目标目录不存在")

    if not dst.type == EntryType.FOLDER:
        http_exceptions.raise_bad_request(E.ENTRY_TARGET_NOT_DIR, "目标不是有效文件夹")

    if dst.is_banned:
        http_exceptions.raise_banned(E.ENTRY_TARGET_BANNED, "目标目录已被封禁，无法执行此操作")

    # 存储 dst 的属性，避免后续数据库操作导致 dst 过期后无法访问
    dst_id = dst.id
    dst_parent_id = dst.parent_id

    # 批量查询所有源对象（单次 SQL）
    all_srcs = await Entry.get(
        session,
        col(Entry.id).in_(request.src_ids) & (Entry.deleted_at == None),
        fetch_mode="all",
    )
    src_list = [
        s for s in all_srcs
        if s.owner_id == user_id and not s.is_banned and s.parent_id is not None and s.id != dst_id
    ]

    # 预计算 dst 的祖先链（循环检测用，只遍历一次）
    ancestor_ids: set[UUID] = set()
    cur_id: UUID | None = dst_parent_id
    while cur_id:
        if cur_id in ancestor_ids:
            break
        ancestor_ids.add(cur_id)
        anc = await Entry.get(session, Entry.id == cur_id)
        cur_id = anc.parent_id if anc else None

    # 一次查出目标目录下所有已有名称（重名检查）
    existing_in_dst = await Entry.get(
        session,
        (Entry.owner_id == user_id) & (Entry.parent_id == dst_id) & (Entry.deleted_at == None),
        fetch_mode="all",
    )
    existing_names = {e.name for e in existing_in_dst}

    moved_count = 0
    for src in src_list:
        # 循环检测：O(1) 查找
        if src.type == EntryType.FOLDER and src.id in ancestor_ids:
            continue

        # 重名检查
        if src.name in existing_names:
            continue

        src.parent_id = dst_id
        await src.save(session, commit=False, refresh=False)
        existing_names.add(src.name)
        moved_count += 1

    # 统一提交所有更改
    await session.commit()


@entry_router.post(
    path='/copies',
    summary='复制对象',
    description='复制一个或多个对象到目标目录。文件复制仅增加物理文件引用计数，不复制物理文件。',
    status_code=204,
    dependencies=[Depends(require_scope("files:create:own"))],
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
        http_exceptions.raise_not_found(E.ENTRY_TARGET_NOT_FOUND, "目标目录不存在")

    if not dst.type == EntryType.FOLDER:
        http_exceptions.raise_bad_request(E.ENTRY_TARGET_NOT_DIR, "目标不是有效文件夹")

    if dst.is_banned:
        http_exceptions.raise_banned(E.ENTRY_TARGET_BANNED, "目标目录已被封禁，无法执行此操作")

    copied_count = 0
    new_ids: list[UUID] = []
    total_copied_size = 0

    # 批量查询所有源对象（单次 SQL）
    all_srcs = await Entry.get(
        session,
        col(Entry.id).in_(request.src_ids) & (Entry.deleted_at == None),
        fetch_mode="all",
    )

    # 预计算 dst 的祖先链（循环检测用，只遍历一次）
    ancestor_ids: set[UUID] = set()
    cur_id: UUID | None = dst.parent_id
    while cur_id:
        if cur_id in ancestor_ids:
            break
        ancestor_ids.add(cur_id)
        anc = await Entry.get(session, Entry.id == cur_id)
        cur_id = anc.parent_id if anc else None

    # 一次查出目标目录下所有已有名称（重名检查）
    existing_in_dst = await Entry.get(
        session,
        (Entry.owner_id == user_id) & (Entry.parent_id == dst.id) & (Entry.deleted_at == None),
        fetch_mode="all",
    )
    existing_names = {e.name for e in existing_in_dst}

    for src in all_srcs:
        if src.owner_id != user_id:
            continue

        if src.is_banned:
            http_exceptions.raise_banned(E.ENTRY_BANNED, "源对象已被封禁，无法执行此操作")

        # 不能复制根目录
        if src.parent_id is None:
            http_exceptions.raise_forbidden(E.ENTRY_COPY_ROOT, "无法复制根目录")

        # 不能复制到自身
        # [TODO] 视为创建副本
        if src.id == dst.id:
            continue

        # 循环检测：O(1) 查找
        if src.type == EntryType.FOLDER and src.id in ancestor_ids:
            continue

        # 重名检查
        if src.name in existing_names:
            # [TODO] 应当询问用户是否覆盖、跳过或创建副本
            continue

        # 递归复制
        count, ids, copied_size = await src.copy_recursive(session, dst.id, user_id)
        copied_count += count
        new_ids.extend(ids)
        total_copied_size += copied_size
        existing_names.add(src.name)

    # 更新用户存储配额
    if total_copied_size > 0:
        await user.adjust_storage(session, total_copied_size)

    l.info(f"用户 {user_id} 复制了 {copied_count} 个对象")


@entry_router.patch(
    path='/{file_id}',
    summary='更新对象',
    description='更新对象属性（如重命名）。',
    status_code=204,
    dependencies=[Depends(require_scope("files:write:own"))],
)
async def router_object_update(
    session: SessionDep,
    user: Annotated[User, Depends(auth_required)],
    file_id: UUID,
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
    :param file_id: 对象UUID（路径参数）
    :param request: 更新请求
    :return: 更新结果
    """
    # 存储 user.id，避免后续 save() 导致 user 过期后无法访问
    user_id = user.id

    # 验证对象存在（排除已删除的）
    obj = await Entry.get(
        session,
        (Entry.id == file_id) & (Entry.deleted_at == None)
    )
    if not obj:
        http_exceptions.raise_not_found(E.ENTRY_NOT_FOUND, "对象不存在")

    if obj.owner_id != user_id:
        http_exceptions.raise_forbidden(E.ENTRY_FORBIDDEN, "无权操作此对象")

    if obj.is_banned:
        http_exceptions.raise_banned()

    # 不能重命名根目录
    if obj.parent_id is None:
        http_exceptions.raise_bad_request(E.ENTRY_ROOT_RENAME, "无法重命名根目录")

    if request.name is not None:
        # 验证新名称格式
        new_name = request.name.strip()
        if not new_name:
            http_exceptions.raise_bad_request(E.ENTRY_NAME_EMPTY, "名称不能为空")

        if '/' in new_name or '\\' in new_name:
            http_exceptions.raise_bad_request(E.ENTRY_NAME_SLASH, "名称不能包含斜杠")

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
            http_exceptions.raise_conflict(E.ENTRY_DUPLICATE, "同名对象已存在")

        # 更新名称
        obj.name = new_name
        obj = await obj.save(session)

        l.info(f"用户 {user_id} 将对象 {obj.id} 重命名为 {new_name}")


@entry_router.get(
    path='/{file_id}',
    summary='获取对象基本属性',
    description='获取对象的基本属性信息（名称、类型、大小、创建/修改时间等）。',
    dependencies=[Depends(require_scope("files:read:own"))],
)
async def router_object_property(
    session: SessionDep,
    user: Annotated[User, Depends(auth_required)],
    file_id: UUID,
) -> EntryPropertyResponse:
    """
    获取对象基本属性端点

    :param session: 数据库会话
    :param user: 当前登录用户
    :param file_id: 对象UUID
    :return: 对象基本属性
    """
    obj = await Entry.get(
        session,
        (Entry.id == file_id) & (Entry.deleted_at == None)
    )
    if not obj:
        http_exceptions.raise_not_found(E.ENTRY_NOT_FOUND, "对象不存在")

    if obj.owner_id != user.id:
        http_exceptions.raise_forbidden(E.ENTRY_VIEW_FORBIDDEN, "无权查看此对象")

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


@entry_router.get(
    path='/{file_id}/detail',
    summary='获取对象详细属性',
    description='获取对象的详细属性信息，包括元数据、分享统计、存储信息等。',
    dependencies=[Depends(require_scope("files:read:own"))],
)
async def router_object_property_detail(
    session: SessionDep,
    user: Annotated[User, Depends(auth_required)],
    file_id: UUID,
) -> EntryPropertyDetailResponse:
    """
    获取对象详细属性端点

    :param session: 数据库会话
    :param user: 当前登录用户
    :param file_id: 对象UUID
    :return: 对象详细属性
    """
    # 预加载 metadata、policy、physical_file 关系（单次查询 + selectinload）
    obj = await Entry.get(
        session,
        (Entry.id == file_id) & (Entry.deleted_at == None),
        load=[Entry.metadata_entries, Entry.policy, Entry.physical_file],
    )
    if not obj:
        http_exceptions.raise_not_found(E.ENTRY_NOT_FOUND, "对象不存在")

    if obj.owner_id != user.id:
        http_exceptions.raise_forbidden(E.ENTRY_VIEW_FORBIDDEN, "无权查看此对象")

    # 策略名称（已预加载）
    policy_name = obj.policy.name if obj.policy else None

    # 分享统计：用数据库聚合代替全量加载
    from sqlalchemy import func
    from sqlmodel import select
    from sqlmodels import Share
    share_stmt = select(
        func.count(Share.id),
        func.coalesce(func.sum(Share.views), 0),
        func.coalesce(func.sum(Share.downloads), 0),
    ).where(Share.file_id == obj.id)
    share_result = await session.exec(share_stmt)
    share_row = share_result.one()
    share_count: int = share_row[0]
    total_views: int = share_row[1]
    total_downloads: int = share_row[2]

    # 物理文件信息（已预加载）
    reference_count = 1
    checksum_md5: str | None = None
    checksum_sha256: str | None = None
    pf = obj.physical_file
    if pf:
        reference_count = pf.reference_count
        checksum_md5 = pf.checksum_md5
        checksum_sha256 = pf.checksum_sha256

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


@entry_router.patch(
    path='/{file_id}/policy',
    summary='切换对象存储策略',
    dependencies=[Depends(require_scope("files:write:own"))],
)
async def router_object_switch_policy(
    session: SessionDep,
    background_tasks: BackgroundTasks,
    user: Annotated[User, Depends(auth_required)],
    file_id: UUID,
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
        (Entry.id == file_id) & (Entry.deleted_at == None)
    )
    if not obj:
        http_exceptions.raise_not_found(E.ENTRY_NOT_FOUND, "对象不存在")
    if obj.owner_id != user_id:
        http_exceptions.raise_forbidden(E.ENTRY_FORBIDDEN, "无权操作此对象")
    if obj.is_banned:
        http_exceptions.raise_banned()

    # 根目录不能直接切换策略（应通过子对象或子目录操作）
    if obj.parent_id is None:
        http_exceptions.raise_bad_request(E.ENTRY_ROOT_POLICY_CHANGE, "不能对根目录切换存储策略，请对子目录操作")

    # 校验目标策略存在
    dest_policy = await Policy.get(session, Policy.id == request.policy_id)
    if not dest_policy:
        http_exceptions.raise_not_found(E.POLICY_NOT_FOUND, "目标存储策略不存在")

    # 校验用户组权限
    group: Group = await user.awaitable_attrs.group
    await session.refresh(group, ['policies'])
    allowed_ids = {p.id for p in group.policies}
    if request.policy_id not in allowed_ids:
        http_exceptions.raise_forbidden(E.POLICY_FORBIDDEN, "当前用户组无权使用该存储策略")

    # 不能切换到相同策略
    if obj.policy_id == request.policy_id:
        http_exceptions.raise_bad_request(E.ENTRY_SAME_POLICY, "目标策略与当前策略相同")

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
        file_id=obj_id,
    )
    task_props = await task_props.save(session)

    if obj_type == EntryType.FILE:
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

@entry_router.get(
    path='/{file_id}/metadata',
    summary='获取对象元数据',
    description='获取对象的元数据键值对，可按命名空间过滤。',
    dependencies=[Depends(require_scope("files:read:own"))],
)
async def router_get_object_metadata(
    session: SessionDep,
    user: Annotated[User, Depends(auth_required)],
    file_id: UUID,
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
        (Entry.id == file_id) & (Entry.deleted_at == None),
        load=Entry.metadata_entries,
    )
    if not obj:
        http_exceptions.raise_not_found(E.ENTRY_NOT_FOUND, "对象不存在")

    if obj.owner_id != user.id:
        http_exceptions.raise_forbidden(E.ENTRY_VIEW_FORBIDDEN, "无权查看此对象")

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


@entry_router.patch(
    path='/{file_id}/metadata',
    summary='批量更新对象元数据',
    description='批量设置或删除对象的元数据条目。仅允许修改 custom: 命名空间。',
    status_code=204,
    dependencies=[Depends(require_scope("files:write:own"))],
)
async def router_patch_object_metadata(
    session: SessionDep,
    user: Annotated[User, Depends(auth_required)],
    file_id: UUID,
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
        (Entry.id == file_id) & (Entry.deleted_at == None),
    )
    if not obj:
        http_exceptions.raise_not_found(E.ENTRY_NOT_FOUND, "对象不存在")

    if obj.owner_id != user.id:
        http_exceptions.raise_forbidden(E.ENTRY_FORBIDDEN, "无权操作此对象")

    # 先验证所有命名空间（快速失败）
    for patch in request.patches:
        patch_ns = patch.key.split(":")[0] if ":" in patch.key else ""
        if patch_ns not in USER_WRITABLE_NAMESPACES:
            http_exceptions.raise_bad_request(
                E.ENTRY_METADATA_NS_FORBIDDEN,
                f"不允许修改命名空间 '{patch_ns}' 的元数据，仅允许 custom: 命名空间",
            )

    # 批量获取该文件的所有现有元数据（单次 SQL）
    all_metadata = await EntryMetadata.get(
        session,
        EntryMetadata.file_id == file_id,
        fetch_mode="all",
    )
    metadata_map: dict[str, EntryMetadata] = {m.name: m for m in all_metadata}

    for patch in request.patches:
        existing = metadata_map.get(patch.key)

        if patch.value is None:
            if existing:
                await EntryMetadata.delete(session, instances=existing, commit=False)
        else:
            if existing:
                existing.value = patch.value
                await existing.save(session, commit=False, refresh=False)
            else:
                entry = EntryMetadata(
                    file_id=file_id,
                    name=patch.key,
                    value=patch.value,
                    is_public=True,
                )
                await entry.save(session, commit=False, refresh=False)

    await session.commit()
    l.info(f"用户 {user.id} 更新了对象 {file_id} 的 {len(request.patches)} 条元数据")
