"""
对象操作路由

提供文件和目录对象的管理功能：删除、移动、复制、重命名等。

路由前缀：/object
"""
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from loguru import logger as l
from sqlmodel.ext.asyncio.session import AsyncSession

from middleware.auth import auth_required
from middleware.dependencies import SessionDep
from models import (
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
    User,
)
from models import ResponseBase
from service.storage import LocalStorageService

object_router = APIRouter(
    prefix="/object",
    tags=["object"]
)


async def _delete_object_recursive(
    session: AsyncSession,
    obj: Object,
    user_id: UUID,
) -> int:
    """
    递归删除对象（软删除）

    对于文件：
    - 减少 PhysicalFile 引用计数
    - 只有引用计数为0时才移动物理文件到回收站

    对于目录：
    - 递归处理所有子对象

    :param session: 数据库会话
    :param obj: 要删除的对象
    :param user_id: 用户UUID
    :return: 删除的对象数量
    """
    deleted_count = 0

    if obj.is_folder:
        # 递归删除子对象
        children = await Object.get_children(session, user_id, obj.id)
        for child in children:
            deleted_count += await _delete_object_recursive(session, child, user_id)

    # 如果是文件，处理物理文件引用
    if obj.is_file and obj.physical_file_id:
        physical_file = await PhysicalFile.get(session, PhysicalFile.id == obj.physical_file_id)
        if physical_file:
            # 减少引用计数
            new_count = physical_file.decrement_reference()

            if physical_file.can_be_deleted:
                # 引用计数为0，移动物理文件到回收站
                policy = await Policy.get(session, Policy.id == physical_file.policy_id)
                if policy and policy.type == PolicyType.LOCAL:
                    try:
                        storage_service = LocalStorageService(policy)
                        await storage_service.move_to_trash(
                            source_path=physical_file.storage_path,
                            user_id=user_id,
                            object_id=obj.id,
                        )
                        l.debug(f"物理文件已移动到回收站: {obj.name}")
                    except Exception as e:
                        l.warning(f"移动物理文件到回收站失败: {obj.name}, 错误: {e}")

                # 删除 PhysicalFile 记录
                await PhysicalFile.delete(session, physical_file)
                l.debug(f"物理文件记录已删除: {physical_file.storage_path}")
            else:
                # 还有其他引用，只更新引用计数
                await physical_file.save(session)
                l.debug(f"物理文件仍有 {new_count} 个引用，不删除: {physical_file.storage_path}")

    # 删除数据库记录
    await Object.delete(session, obj)
    deleted_count += 1

    return deleted_count


async def _copy_object_recursive(
    session: AsyncSession,
    src: Object,
    dst_parent_id: UUID,
    user_id: UUID,
) -> tuple[int, list[UUID]]:
    """
    递归复制对象

    对于文件：
    - 增加 PhysicalFile 引用计数
    - 创建新的 Object 记录指向同一 PhysicalFile

    对于目录：
    - 创建新目录
    - 递归复制所有子对象

    :param session: 数据库会话
    :param src: 源对象
    :param dst_parent_id: 目标父目录UUID
    :param user_id: 用户UUID
    :return: (复制数量, 新对象UUID列表)
    """
    copied_count = 0
    new_ids: list[UUID] = []

    # 创建新的 Object 记录
    new_obj = Object(
        name=src.name,
        type=src.type,
        size=src.size,
        password=src.password,
        parent_id=dst_parent_id,
        owner_id=user_id,
        policy_id=src.policy_id,
        physical_file_id=src.physical_file_id,
    )

    # 如果是文件，增加物理文件引用计数
    if src.is_file and src.physical_file_id:
        physical_file = await PhysicalFile.get(session, PhysicalFile.id == src.physical_file_id)
        if physical_file:
            physical_file.increment_reference()
            await physical_file.save(session)

    new_obj = await new_obj.save(session)
    copied_count += 1
    new_ids.append(new_obj.id)

    # 如果是目录，递归复制子对象
    if src.is_folder:
        children = await Object.get_children(session, user_id, src.id)
        for child in children:
            child_count, child_ids = await _copy_object_recursive(
                session, child, new_obj.id, user_id
            )
            copied_count += child_count
            new_ids.extend(child_ids)

    return copied_count, new_ids


@object_router.delete(
    path='/',
    summary='删除对象',
    description='删除一个或多个对象（文件或目录），文件会移动到用户回收站。',
)
async def router_object_delete(
    session: SessionDep,
    user: Annotated[User, Depends(auth_required)],
    request: ObjectDeleteRequest,
) -> ResponseBase:
    """
    删除对象端点（软删除）

    流程：
    1. 验证对象存在且属于当前用户
    2. 对于文件，减少物理文件引用计数
    3. 如果引用计数为0，移动物理文件到 .trash 目录
    4. 对于目录，递归处理子对象
    5. 从数据库中删除记录

    :param session: 数据库会话
    :param user: 当前登录用户
    :param request: 删除请求（包含待删除对象的UUID列表）
    :return: 删除结果
    """
    # 存储 user.id，避免后续 save() 导致 user 过期后无法访问
    user_id = user.id
    deleted_count = 0

    for obj_id in request.ids:
        obj = await Object.get(session, Object.id == obj_id)
        if not obj or obj.owner_id != user_id:
            continue

        # 不能删除根目录
        if obj.parent_id is None:
            l.warning(f"尝试删除根目录被阻止: {obj.name}")
            continue

        # 递归删除（包含引用计数逻辑）
        count = await _delete_object_recursive(session, obj, user_id)
        deleted_count += count

    l.info(f"用户 {user_id} 删除了 {deleted_count} 个对象")

    return ResponseBase(
        data={
            "deleted": deleted_count,
            "total": len(request.ids),
        }
    )


@object_router.patch(
    path='/',
    summary='移动对象',
    description='移动一个或多个对象到目标目录',
)
async def router_object_move(
    session: SessionDep,
    user: Annotated[User, Depends(auth_required)],
    request: ObjectMoveRequest,
) -> ResponseBase:
    """
    移动对象端点

    :param session: 数据库会话
    :param user: 当前登录用户
    :param request: 移动请求（包含源对象UUID列表和目标目录UUID）
    :return: 移动结果
    """
    # 存储 user.id，避免后续 save() 导致 user 过期后无法访问
    user_id = user.id

    # 验证目标目录
    dst = await Object.get(session, Object.id == request.dst_id)
    if not dst or dst.owner_id != user_id:
        raise HTTPException(status_code=404, detail="目标目录不存在")

    if not dst.is_folder:
        raise HTTPException(status_code=400, detail="目标不是有效文件夹")

    moved_count = 0

    for src_id in request.src_ids:
        src = await Object.get(session, Object.id == src_id)
        if not src or src.owner_id != user_id:
            continue

        # 不能移动根目录
        if src.parent_id is None:
            continue

        # 检查是否移动到自身或子目录（防止循环引用）
        if src.id == dst.id:
            continue

        # 检查是否将目录移动到其子目录中（循环检测）
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

        # 检查目标目录下是否存在同名对象
        existing = await Object.get(
            session,
            (Object.owner_id == user_id) &
            (Object.parent_id == dst.id) &
            (Object.name == src.name)
        )
        if existing:
            continue  # 跳过重名对象

        src.parent_id = dst.id
        await src.save(session)
        moved_count += 1

    return ResponseBase(
        data={
            "moved": moved_count,
            "total": len(request.src_ids),
        }
    )


@object_router.post(
    path='/copy',
    summary='复制对象',
    description='复制一个或多个对象到目标目录。文件复制仅增加物理文件引用计数，不复制物理文件。',
)
async def router_object_copy(
    session: SessionDep,
    user: Annotated[User, Depends(auth_required)],
    request: ObjectCopyRequest,
) -> ResponseBase:
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

    # 验证目标目录
    dst = await Object.get(session, Object.id == request.dst_id)
    if not dst or dst.owner_id != user_id:
        raise HTTPException(status_code=404, detail="目标目录不存在")

    if not dst.is_folder:
        raise HTTPException(status_code=400, detail="目标不是有效文件夹")

    copied_count = 0
    new_ids: list[UUID] = []

    for src_id in request.src_ids:
        src = await Object.get(session, Object.id == src_id)
        if not src or src.owner_id != user_id:
            continue

        # 不能复制根目录
        if src.parent_id is None:
            continue

        # 不能复制到自身
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

        # 检查目标目录下是否存在同名对象
        existing = await Object.get(
            session,
            (Object.owner_id == user_id) &
            (Object.parent_id == dst.id) &
            (Object.name == src.name)
        )
        if existing:
            continue  # 跳过重名对象

        # 递归复制
        count, ids = await _copy_object_recursive(session, src, dst.id, user_id)
        copied_count += count
        new_ids.extend(ids)

    l.info(f"用户 {user_id} 复制了 {copied_count} 个对象")

    return ResponseBase(
        data={
            "copied": copied_count,
            "total": len(request.src_ids),
            "new_ids": new_ids,
        }
    )


@object_router.post(
    path='/rename',
    summary='重命名对象',
    description='重命名对象（文件或目录）。',
)
async def router_object_rename(
    session: SessionDep,
    user: Annotated[User, Depends(auth_required)],
    request: ObjectRenameRequest,
) -> ResponseBase:
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

    # 验证对象存在
    obj = await Object.get(session, Object.id == request.id)
    if not obj:
        raise HTTPException(status_code=404, detail="对象不存在")

    if obj.owner_id != user_id:
        raise HTTPException(status_code=403, detail="无权操作此对象")

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

    # 检查同目录下是否存在同名对象
    existing = await Object.get(
        session,
        (Object.owner_id == user_id) &
        (Object.parent_id == obj.parent_id) &
        (Object.name == new_name)
    )
    if existing:
        raise HTTPException(status_code=409, detail="同名对象已存在")

    # 更新名称
    obj.name = new_name
    await obj.save(session)

    l.info(f"用户 {user_id} 将对象 {obj.id} 重命名为 {new_name}")

    return ResponseBase(data={"success": True})


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
    obj = await Object.get(session, Object.id == id)
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
        Object.id == id,
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
    from models import Share
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
