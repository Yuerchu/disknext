from datetime import datetime
from uuid import UUID

from loguru import logger as l
from sqlalchemy import update as sql_update
from sqlalchemy.sql.functions import func
from middleware.dependencies import SessionDep

from .local_storage import LocalStorageService
from .s3_storage import S3StorageService
from sqlmodels import (
    Object,
    PhysicalFile,
    Policy,
    PolicyType,
    User,
)


async def adjust_user_storage(
    session: SessionDep,
    user_id: UUID,
    delta: int,
    commit: bool = True,
) -> None:
    """
    原子更新用户已用存储空间

    使用 SQL UPDATE SET storage = GREATEST(0, storage + delta) 避免竞态条件。

    :param session: 数据库会话
    :param user_id: 用户UUID
    :param delta: 变化量（正数增加，负数减少）
    :param commit: 是否立即提交
    """
    if delta == 0:
        return

    stmt = (
        sql_update(User)
        .where(User.id == user_id)
        .values(storage=func.greatest(0, User.storage + delta))
    )
    await session.execute(stmt)

    if commit:
        await session.commit()

    l.debug(f"用户 {user_id} 存储配额变更: {'+' if delta > 0 else ''}{delta} bytes")


# ==================== 软删除 ====================

async def soft_delete_objects(
    session: SessionDep,
    objects: list[Object],
) -> int:
    """
    软删除对象列表

    只标记顶层对象：设置 deleted_at、保存原 parent_id 到 deleted_original_parent_id、
    将 parent_id 置 NULL 脱离文件树。子对象保持不变，物理文件不移动。

    :param session: 数据库会话
    :param objects: 待软删除的对象列表
    :return: 软删除的对象数量
    """
    deleted_count = 0
    now = datetime.now()

    for obj in objects:
        obj.deleted_at = now
        obj.deleted_original_parent_id = obj.parent_id
        obj.parent_id = None
        await obj.save(session, commit=False, refresh=False)
        deleted_count += 1

    await session.commit()
    return deleted_count


# ==================== 恢复 ====================

async def _resolve_name_conflict(
    session: SessionDep,
    user_id: UUID,
    parent_id: UUID,
    name: str,
) -> str:
    """
    解决同名冲突，返回不冲突的名称

    命名规则：原名称 → 原名称 (1) → 原名称 (2) → ...
    对于有扩展名的文件：name.ext → name (1).ext → name (2).ext → ...

    :param session: 数据库会话
    :param user_id: 用户UUID
    :param parent_id: 父目录UUID
    :param name: 原始名称
    :return: 不冲突的名称
    """
    existing = await Object.get(
        session,
        (Object.owner_id == user_id) &
        (Object.parent_id == parent_id) &
        (Object.name == name) &
        (Object.deleted_at == None)
    )
    if not existing:
        return name

    # 分离文件名和扩展名
    if '.' in name:
        base, ext = name.rsplit('.', 1)
        ext = f".{ext}"
    else:
        base = name
        ext = ""

    counter = 1
    while True:
        new_name = f"{base} ({counter}){ext}"
        existing = await Object.get(
            session,
            (Object.owner_id == user_id) &
            (Object.parent_id == parent_id) &
            (Object.name == new_name) &
            (Object.deleted_at == None)
        )
        if not existing:
            return new_name
        counter += 1


async def restore_objects(
    session: SessionDep,
    objects: list[Object],
    user_id: UUID,
) -> int:
    """
    从回收站恢复对象

    检查原父目录是否存在且未删除：
    - 存在 → 恢复到原位置
    - 不存在 → 恢复到用户根目录
    处理同名冲突（自动重命名）。

    :param session: 数据库会话
    :param objects: 待恢复的对象列表（必须是回收站中的顶层对象）
    :param user_id: 用户UUID
    :return: 恢复的对象数量
    """
    root = await Object.get_root(session, user_id)
    if not root:
        raise ValueError("用户根目录不存在")

    restored_count = 0

    for obj in objects:
        if not obj.deleted_at:
            continue

        # 确定恢复目标目录
        target_parent_id = root.id
        if obj.deleted_original_parent_id:
            original_parent = await Object.get(
                session,
                (Object.id == obj.deleted_original_parent_id) & (Object.deleted_at == None)
            )
            if original_parent:
                target_parent_id = original_parent.id

        # 解决同名冲突
        resolved_name = await _resolve_name_conflict(
            session, user_id, target_parent_id, obj.name
        )

        # 恢复对象
        obj.parent_id = target_parent_id
        obj.deleted_at = None
        obj.deleted_original_parent_id = None
        if resolved_name != obj.name:
            obj.name = resolved_name
        await obj.save(session, commit=False, refresh=False)
        restored_count += 1

    await session.commit()
    return restored_count


# ==================== 永久删除 ====================

async def _collect_file_entries_all(
    session: SessionDep,
    user_id: UUID,
    root: Object,
) -> tuple[list[tuple[UUID, str, UUID]], int, int]:
    """
    BFS 收集子树中所有文件的物理文件信息（包含已删除和未删除的子对象）

    只执行 SELECT 查询，不触发 commit，ORM 对象始终有效。

    :param session: 数据库会话
    :param user_id: 用户UUID
    :param root: 根对象
    :return: (文件条目列表[(obj_id, name, physical_file_id)], 总对象数, 总文件大小)
    """
    file_entries: list[tuple[UUID, str, UUID]] = []
    total_count = 1
    total_file_size = 0

    # 根对象本身是文件
    if root.is_file and root.physical_file_id:
        file_entries.append((root.id, root.name, root.physical_file_id))
        total_file_size += root.size

    # BFS 遍历子目录（使用 get_all_children 包含所有子对象）
    if root.is_folder:
        queue: list[UUID] = [root.id]
        while queue:
            parent_id = queue.pop(0)
            children = await Object.get_all_children(session, user_id, parent_id)
            for child in children:
                total_count += 1
                if child.is_file and child.physical_file_id:
                    file_entries.append((child.id, child.name, child.physical_file_id))
                    total_file_size += child.size
                elif child.is_folder:
                    queue.append(child.id)

    return file_entries, total_count, total_file_size


async def permanently_delete_objects(
    session: SessionDep,
    objects: list[Object],
    user_id: UUID,
) -> int:
    """
    永久删除回收站中的对象

    验证对象在回收站中（deleted_at IS NOT NULL），
    BFS 收集所有子文件的 PhysicalFile 信息，
    处理引用计数，引用为 0 时物理删除文件，
    最后硬删除根 Object（CASCADE 自动清理子对象）。

    :param session: 数据库会话
    :param objects: 待永久删除的对象列表
    :param user_id: 用户UUID
    :return: 永久删除的对象数量
    """
    total_deleted = 0

    for obj in objects:
        if not obj.deleted_at:
            l.warning(f"对象 {obj.id} 不在回收站中，跳过永久删除")
            continue

        root_id = obj.id
        file_entries, obj_count, total_file_size = await _collect_file_entries_all(
            session, user_id, obj
        )

        # 处理 PhysicalFile 引用计数
        for obj_id, obj_name, physical_file_id in file_entries:
            physical_file = await PhysicalFile.get(session, PhysicalFile.id == physical_file_id)
            if not physical_file:
                continue

            physical_file.decrement_reference()

            if physical_file.can_be_deleted:
                # 物理删除文件
                policy = await Policy.get(session, Policy.id == physical_file.policy_id)
                if policy:
                    try:
                        if policy.type == PolicyType.LOCAL:
                            storage_service = LocalStorageService(policy)
                            await storage_service.delete_file(physical_file.storage_path)
                        elif policy.type == PolicyType.S3:
                            s3_service = await S3StorageService.from_policy(policy)
                            await s3_service.delete_file(physical_file.storage_path)
                        l.debug(f"物理文件已删除: {obj_name}")
                    except Exception as e:
                        l.warning(f"物理删除文件失败: {obj_name}, 错误: {e}")

                await PhysicalFile.delete(session, physical_file, commit=False)
                l.debug(f"物理文件记录已删除: {physical_file.storage_path}")
            else:
                await physical_file.save(session, commit=False)
                l.debug(f"物理文件仍有 {physical_file.reference_count} 个引用: {physical_file.storage_path}")

        # 更新用户存储配额
        if total_file_size > 0:
            await adjust_user_storage(session, user_id, -total_file_size, commit=False)

        # 硬删除根对象，CASCADE 自动删除所有子对象（不立即提交，避免其余对象过期）
        await Object.delete(session, condition=Object.id == root_id, commit=False)

        total_deleted += obj_count

    # 统一提交所有变更
    await session.commit()
    return total_deleted


# ==================== 旧接口（保持向后兼容） ====================

async def _collect_file_entries(
    session: SessionDep,
    user_id: UUID,
    root: Object,
) -> tuple[list[tuple[UUID, str, UUID]], int, int]:
    """
    BFS 收集子树中所有文件的物理文件信息

    只执行 SELECT 查询，不触发 commit，ORM 对象始终有效。

    :param session: 数据库会话
    :param user_id: 用户UUID
    :param root: 根对象
    :return: (文件条目列表[(obj_id, name, physical_file_id)], 总对象数, 总文件大小)
    """
    file_entries: list[tuple[UUID, str, UUID]] = []
    total_count = 1
    total_file_size = 0

    # 根对象本身是文件
    if root.is_file and root.physical_file_id:
        file_entries.append((root.id, root.name, root.physical_file_id))
        total_file_size += root.size

    # BFS 遍历子目录
    if root.is_folder:
        queue: list[UUID] = [root.id]
        while queue:
            parent_id = queue.pop(0)
            children = await Object.get_children(session, user_id, parent_id)
            for child in children:
                total_count += 1
                if child.is_file and child.physical_file_id:
                    file_entries.append((child.id, child.name, child.physical_file_id))
                    total_file_size += child.size
                elif child.is_folder:
                    queue.append(child.id)

    return file_entries, total_count, total_file_size


async def delete_object_recursive(
    session: SessionDep,
    obj: Object,
    user_id: UUID,
) -> int:
    """
    删除对象及其所有子对象（硬删除）

    两阶段策略：
    1. BFS 只读收集所有文件的 PhysicalFile 信息
    2. 批量处理引用计数（commit=False），最后删除根对象触发 CASCADE

    :param session: 数据库会话
    :param obj: 要删除的对象
    :param user_id: 用户UUID
    :return: 删除的对象数量
    """
    # 阶段一：只读收集（不触发任何 commit）
    root_id = obj.id
    file_entries, total_count, total_file_size = await _collect_file_entries(session, user_id, obj)

    # 阶段二：批量处理 PhysicalFile 引用（全部 commit=False）
    for obj_id, obj_name, physical_file_id in file_entries:
        physical_file = await PhysicalFile.get(session, PhysicalFile.id == physical_file_id)
        if not physical_file:
            continue

        physical_file.decrement_reference()

        if physical_file.can_be_deleted:
            # 物理删除文件
            policy = await Policy.get(session, Policy.id == physical_file.policy_id)
            if policy:
                try:
                    if policy.type == PolicyType.LOCAL:
                        storage_service = LocalStorageService(policy)
                        await storage_service.delete_file(physical_file.storage_path)
                    elif policy.type == PolicyType.S3:
                        options = await policy.awaitable_attrs.options
                        s3_service = S3StorageService(
                            policy,
                            region=options.s3_region if options else 'us-east-1',
                            is_path_style=options.s3_path_style if options else False,
                        )
                        await s3_service.delete_file(physical_file.storage_path)
                    l.debug(f"物理文件已删除: {obj_name}")
                except Exception as e:
                    l.warning(f"物理删除文件失败: {obj_name}, 错误: {e}")

            await PhysicalFile.delete(session, physical_file, commit=False)
            l.debug(f"物理文件记录已删除: {physical_file.storage_path}")
        else:
            await physical_file.save(session, commit=False)
            l.debug(f"物理文件仍有 {physical_file.reference_count} 个引用: {physical_file.storage_path}")

    # 阶段三：更新用户存储配额（与删除在同一事务中）
    if total_file_size > 0:
        await adjust_user_storage(session, user_id, -total_file_size, commit=False)

    # 阶段四：删除根对象，数据库 CASCADE 自动删除所有子对象
    # commit=True（默认），一次性提交所有 PhysicalFile 变更 + Object 删除 + 配额更新
    await Object.delete(session, condition=Object.id == root_id)

    return total_count


# ==================== 复制 ====================

async def _copy_object_recursive(
    session: SessionDep,
    src: Object,
    dst_parent_id: UUID,
    user_id: UUID,
) -> tuple[int, list[UUID], int]:
    """
    递归复制对象（内部实现）

    :param session: 数据库会话
    :param src: 源对象
    :param dst_parent_id: 目标父目录UUID
    :param user_id: 用户UUID
    :return: (复制数量, 新对象UUID列表, 复制的总文件大小)
    """
    copied_count = 0
    new_ids: list[UUID] = []
    total_copied_size = 0

    # 在 save() 之前保存需要的属性值，避免 commit 后对象过期导致懒加载失败
    src_is_folder = src.is_folder
    src_is_file = src.is_file
    src_id = src.id
    src_size = src.size
    src_physical_file_id = src.physical_file_id

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
    if src_is_file and src_physical_file_id:
        physical_file = await PhysicalFile.get(session, PhysicalFile.id == src_physical_file_id)
        if physical_file:
            physical_file.increment_reference()
            await physical_file.save(session)
        total_copied_size += src_size

    new_obj = await new_obj.save(session)
    copied_count += 1
    new_ids.append(new_obj.id)

    # 如果是目录，递归复制子对象
    if src_is_folder:
        children = await Object.get_children(session, user_id, src_id)
        for child in children:
            child_count, child_ids, child_size = await _copy_object_recursive(
                session, child, new_obj.id, user_id
            )
            copied_count += child_count
            new_ids.extend(child_ids)
            total_copied_size += child_size

    return copied_count, new_ids, total_copied_size


async def copy_object_recursive(
    session: SessionDep,
    src: Object,
    dst_parent_id: UUID,
    user_id: UUID,
) -> tuple[int, list[UUID], int]:
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
    :return: (复制数量, 新对象UUID列表, 复制的总文件大小)
    """
    return await _copy_object_recursive(session, src, dst_parent_id, user_id)
