"""
对象操作路由

提供文件和目录对象的管理功能：删除、移动、复制、重命名等。

路由前缀：/object
"""
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from loguru import logger as l

from middleware.auth import auth_required
from middleware.dependencies import SessionDep
from sqlmodels import (
    CreateFileRequest,
    Object,
    ObjectCopyRequest,
    ObjectDeleteRequest,
    ObjectMoveRequest,
    ObjectPropertyDetailResponse,
    ObjectPropertyResponse,
    ObjectRenameRequest,
    ObjectType,
    PhysicalFile,
    Policy,
    PolicyType,
    ResponseBase,
    User,
)
from service.storage import (
    LocalStorageService,
    adjust_user_storage,
    copy_object_recursive,
)
from service.storage.object import soft_delete_objects
from utils import http_exceptions

object_router = APIRouter(
    prefix="/object",
    tags=["object"]
)

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
    parent = await Object.get(
        session,
        (Object.id == request.parent_id) & (Object.deleted_at == None)
    )
    if not parent or parent.owner_id != user_id:
        raise HTTPException(status_code=404, detail="父目录不存在")

    if not parent.is_folder:
        raise HTTPException(status_code=400, detail="父对象不是目录")

    if parent.is_banned:
        http_exceptions.raise_banned("目标目录已被封禁，无法执行此操作")

    # 检查是否已存在同名文件（仅检查未删除的）
    existing = await Object.get(
        session,
        (Object.owner_id == user_id) &
        (Object.parent_id == parent.id) &
        (Object.name == request.name) &
        (Object.deleted_at == None)
    )
    if existing:
        raise HTTPException(status_code=409, detail="同名文件已存在")

    # 确定存储策略
    policy_id = request.policy_id or parent.policy_id
    policy = await Policy.get(session, Policy.id == policy_id)
    if not policy:
        raise HTTPException(status_code=404, detail="存储策略不存在")

    parent_id = parent.id

    # 生成存储路径并创建空文件
    if policy.type == PolicyType.LOCAL:
        storage_service = LocalStorageService(policy)
        dir_path, storage_name, full_path = await storage_service.generate_file_path(
            user_id=user_id,
            original_filename=request.name,
        )
        await storage_service.create_empty_file(full_path)
        storage_path = full_path
    else:
        raise HTTPException(status_code=501, detail="S3 存储暂未实现")

    # 创建 PhysicalFile 记录
    physical_file = PhysicalFile(
        storage_path=storage_path,
        size=0,
        policy_id=policy_id,
        reference_count=1,
    )
    physical_file = await physical_file.save(session)

    # 创建 Object 记录
    file_object = Object(
        name=request.name,
        type=ObjectType.FILE,
        size=0,
        physical_file_id=physical_file.id,
        parent_id=parent_id,
        owner_id=user_id,
        policy_id=policy_id,
    )
    await file_object.save(session)

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
    request: ObjectDeleteRequest,
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
    objects_to_delete: list[Object] = []

    for obj_id in request.ids:
        obj = await Object.get(
            session,
            (Object.id == obj_id) & (Object.deleted_at == None)
        )
        if not obj or obj.owner_id != user_id:
            continue

        # 不能删除根目录
        if obj.parent_id is None:
            l.warning(f"尝试删除根目录被阻止: {obj.name}")
            continue

        objects_to_delete.append(obj)

    if objects_to_delete:
        deleted_count = await soft_delete_objects(session, objects_to_delete)
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
    request: ObjectMoveRequest,
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
    dst = await Object.get(
        session,
        (Object.id == request.dst_id) & (Object.deleted_at == None)
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
        src = await Object.get(
            session,
            (Object.id == src_id) & (Object.deleted_at == None)
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
                current = await Object.get(session, Object.id == current_parent_id)
                current_parent_id = current.parent_id if current else None
            if is_cycle:
                continue

        # 检查目标目录下是否存在同名对象（仅检查未删除的）
        existing = await Object.get(
            session,
            (Object.owner_id == user_id) &
            (Object.parent_id == dst_id) &
            (Object.name == src.name) &
            (Object.deleted_at == None)
        )
        if existing:
            continue  # 跳过重名对象

        src.parent_id = dst_id
        await src.save(session, commit=False, refresh=False)
        moved_count += 1

    # 统一提交所有更改
    await session.commit()


@object_router.post(
    path='/copy',
    summary='复制对象',
    description='复制一个或多个对象到目标目录。文件复制仅增加物理文件引用计数，不复制物理文件。',
    status_code=204,
)
async def router_object_copy(
    session: SessionDep,
    user: Annotated[User, Depends(auth_required)],
    request: ObjectCopyRequest,
) -> None:
    """
    复制对象端点

    流程：
    1. 验证目标目录存在且属于当前用户
    2. 对于每个源对象：
       - 验证源对象存在且属于当前用户
       - 检查目标目录下是否存在同名对象
       - 如果是文件：增加 PhysicalFile 引用计数，创建新 Object
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
    dst = await Object.get(
        session,
        (Object.id == request.dst_id) & (Object.deleted_at == None)
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
        src = await Object.get(
            session,
            (Object.id == src_id) & (Object.deleted_at == None)
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
                current = await Object.get(session, Object.id == current.parent_id)
            if is_cycle:
                continue

        # 检查目标目录下是否存在同名对象（仅检查未删除的）
        existing = await Object.get(
            session,
            (Object.owner_id == user_id) &
            (Object.parent_id == dst.id) &
            (Object.name == src.name) &
            (Object.deleted_at == None)
        )
        if existing:
            # [TODO] 应当询问用户是否覆盖、跳过或创建副本
            continue

        # 递归复制
        count, ids, copied_size = await copy_object_recursive(session, src, dst.id, user_id)
        copied_count += count
        new_ids.extend(ids)
        total_copied_size += copied_size

    # 更新用户存储配额
    if total_copied_size > 0:
        await adjust_user_storage(session, user_id, total_copied_size)

    l.info(f"用户 {user_id} 复制了 {copied_count} 个对象")


@object_router.post(
    path='/rename',
    summary='重命名对象',
    description='重命名对象（文件或目录）。',
    status_code=204,
)
async def router_object_rename(
    session: SessionDep,
    user: Annotated[User, Depends(auth_required)],
    request: ObjectRenameRequest,
) -> None:
    """
    重命名对象端点

    流程：
    1. 验证对象存在且属于当前用户
    2. 验证新名称格式（不含非法字符）
    3. 检查同目录下是否存在同名对象
    4. 更新 name 字段
    5. 返回更新结果

    :param session: 数据库会话
    :param user: 当前登录用户
    :param request: 重命名请求
    :return: 重命名结果
    """
    # 存储 user.id，避免后续 save() 导致 user 过期后无法访问
    user_id = user.id

    # 验证对象存在（排除已删除的）
    obj = await Object.get(
        session,
        (Object.id == request.id) & (Object.deleted_at == None)
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

    # 验证新名称格式
    new_name = request.new_name.strip()
    if not new_name:
        raise HTTPException(status_code=400, detail="名称不能为空")

    if '/' in new_name or '\\' in new_name:
        raise HTTPException(status_code=400, detail="名称不能包含斜杠")

    # 如果名称没有变化，直接返回成功
    if obj.name == new_name:
        return ResponseBase(data={"success": True})

    # 检查同目录下是否存在同名对象（仅检查未删除的）
    existing = await Object.get(
        session,
        (Object.owner_id == user_id) &
        (Object.parent_id == obj.parent_id) &
        (Object.name == new_name) &
        (Object.deleted_at == None)
    )
    if existing:
        raise HTTPException(status_code=409, detail="同名对象已存在")

    # 更新名称
    obj.name = new_name
    await obj.save(session)

    l.info(f"用户 {user_id} 将对象 {obj.id} 重命名为 {new_name}")


@object_router.get(
    path='/property/{id}',
    summary='获取对象基本属性',
    description='获取对象的基本属性信息（名称、类型、大小、创建/修改时间等）。',
)
async def router_object_property(
    session: SessionDep,
    user: Annotated[User, Depends(auth_required)],
    id: UUID,
) -> ObjectPropertyResponse:
    """
    获取对象基本属性端点

    :param session: 数据库会话
    :param user: 当前登录用户
    :param id: 对象UUID
    :return: 对象基本属性
    """
    obj = await Object.get(
        session,
        (Object.id == id) & (Object.deleted_at == None)
    )
    if not obj:
        raise HTTPException(status_code=404, detail="对象不存在")

    if obj.owner_id != user.id:
        raise HTTPException(status_code=403, detail="无权查看此对象")

    return ObjectPropertyResponse(
        id=obj.id,
        name=obj.name,
        type=obj.type,
        size=obj.size,
        created_at=obj.created_at,
        updated_at=obj.updated_at,
        parent_id=obj.parent_id,
    )


@object_router.get(
    path='/property/{id}/detail',
    summary='获取对象详细属性',
    description='获取对象的详细属性信息，包括元数据、分享统计、存储信息等。',
)
async def router_object_property_detail(
    session: SessionDep,
    user: Annotated[User, Depends(auth_required)],
    id: UUID,
) -> ObjectPropertyDetailResponse:
    """
    获取对象详细属性端点

    :param session: 数据库会话
    :param user: 当前登录用户
    :param id: 对象UUID
    :return: 对象详细属性
    """
    obj = await Object.get(
        session,
        (Object.id == id) & (Object.deleted_at == None),
        load=Object.file_metadata,
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

    # 获取物理文件引用计数
    reference_count = 1
    if obj.physical_file_id:
        physical_file = await PhysicalFile.get(session, PhysicalFile.id == obj.physical_file_id)
        if physical_file:
            reference_count = physical_file.reference_count

    # 构建响应
    response = ObjectPropertyDetailResponse(
        id=obj.id,
        name=obj.name,
        type=obj.type,
        size=obj.size,
        created_at=obj.created_at,
        updated_at=obj.updated_at,
        parent_id=obj.parent_id,
        policy_name=policy_name,
        share_count=share_count,
        total_views=total_views,
        total_downloads=total_downloads,
        reference_count=reference_count,
    )

    # 添加文件元数据
    if obj.file_metadata:
        response.mime_type = obj.file_metadata.mime_type
        response.width = obj.file_metadata.width
        response.height = obj.file_metadata.height
        response.duration = obj.file_metadata.duration
        response.checksum_md5 = obj.file_metadata.checksum_md5

    return response
