"""
存储策略迁移服务

提供跨存储策略的文件迁移功能：
- 单文件迁移：从源策略下载 → 上传到目标策略 → 更新数据库记录
- 目录批量迁移：递归遍历目录下所有文件逐个迁移，同时更新子目录的 policy_id
"""
from uuid import UUID

from loguru import logger as l
from sqlmodel.ext.asyncio.session import AsyncSession

from sqlmodels.object import Object, ObjectType
from sqlmodels.physical_file import PhysicalFile
from sqlmodels.policy import Policy, PolicyType
from sqlmodels.task import Task, TaskStatus

from .local_storage import LocalStorageService
from .s3_storage import S3StorageService


async def _get_storage_service(
        policy: Policy,
) -> LocalStorageService | S3StorageService:
    """
    根据策略类型创建对应的存储服务实例

    :param policy: 存储策略
    :return: 存储服务实例
    """
    if policy.type == PolicyType.LOCAL:
        return LocalStorageService(policy)
    elif policy.type == PolicyType.S3:
        return await S3StorageService.from_policy(policy)
    else:
        raise ValueError(f"不支持的存储策略类型: {policy.type}")


async def _read_file_from_storage(
        service: LocalStorageService | S3StorageService,
        storage_path: str,
) -> bytes:
    """
    从存储服务读取文件内容

    :param service: 存储服务实例
    :param storage_path: 文件存储路径
    :return: 文件二进制内容
    """
    if isinstance(service, LocalStorageService):
        return await service.read_file(storage_path)
    else:
        return await service.download_file(storage_path)


async def _write_file_to_storage(
        service: LocalStorageService | S3StorageService,
        storage_path: str,
        data: bytes,
) -> None:
    """
    将文件内容写入存储服务

    :param service: 存储服务实例
    :param storage_path: 文件存储路径
    :param data: 文件二进制内容
    """
    if isinstance(service, LocalStorageService):
        await service.write_file(storage_path, data)
    else:
        await service.upload_file(storage_path, data)


async def _delete_file_from_storage(
        service: LocalStorageService | S3StorageService,
        storage_path: str,
) -> None:
    """
    从存储服务删除文件

    :param service: 存储服务实例
    :param storage_path: 文件存储路径
    """
    if isinstance(service, LocalStorageService):
        await service.delete_file(storage_path)
    else:
        await service.delete_file(storage_path)


async def migrate_single_file(
        session: AsyncSession,
        obj: Object,
        dest_policy: Policy,
) -> None:
    """
    将单个文件对象从当前存储策略迁移到目标策略

    流程：
    1. 获取源物理文件和存储服务
    2. 读取源文件内容
    3. 在目标存储中生成新路径并写入
    4. 创建新的 PhysicalFile 记录
    5. 更新 Object 的 policy_id 和 physical_file_id
    6. 旧 PhysicalFile 引用计数 -1，如为 0 则删除源物理文件

    :param session: 数据库会话
    :param obj: 待迁移的文件对象（必须为文件类型）
    :param dest_policy: 目标存储策略
    """
    if obj.type != ObjectType.FILE:
        raise ValueError(f"只能迁移文件对象，当前类型: {obj.type}")

    # 获取源策略和物理文件
    src_policy: Policy = await obj.awaitable_attrs.policy
    old_physical: PhysicalFile | None = await obj.awaitable_attrs.physical_file

    if not old_physical:
        l.warning(f"文件 {obj.id} 没有关联物理文件，跳过迁移")
        return

    if src_policy.id == dest_policy.id:
        l.debug(f"文件 {obj.id} 已在目标策略中，跳过")
        return

    # 1. 从源存储读取文件
    src_service = await _get_storage_service(src_policy)
    data = await _read_file_from_storage(src_service, old_physical.storage_path)

    # 2. 在目标存储生成新路径并写入
    dest_service = await _get_storage_service(dest_policy)
    _dir_path, _storage_name, new_storage_path = await dest_service.generate_file_path(
        user_id=obj.owner_id,
        original_filename=obj.name,
    )
    await _write_file_to_storage(dest_service, new_storage_path, data)

    # 3. 创建新的 PhysicalFile
    new_physical = PhysicalFile(
        storage_path=new_storage_path,
        size=old_physical.size,
        checksum_md5=old_physical.checksum_md5,
        policy_id=dest_policy.id,
        reference_count=1,
    )
    new_physical = await new_physical.save(session)

    # 4. 更新 Object
    obj.policy_id = dest_policy.id
    obj.physical_file_id = new_physical.id
    await obj.save(session)

    # 5. 旧 PhysicalFile 引用计数 -1
    old_physical.decrement_reference()
    if old_physical.can_be_deleted:
        # 删除源存储中的物理文件
        try:
            await _delete_file_from_storage(src_service, old_physical.storage_path)
        except Exception as e:
            l.warning(f"删除源文件失败（不影响迁移结果）: {old_physical.storage_path}: {e}")
        await PhysicalFile.delete(session, old_physical)
    else:
        await old_physical.save(session)

    l.info(f"文件迁移完成: {obj.name} ({obj.id}), {src_policy.name} → {dest_policy.name}")


async def migrate_file_with_task(
        session: AsyncSession,
        obj: Object,
        dest_policy: Policy,
        task: Task,
) -> None:
    """
    迁移单个文件并更新任务状态

    :param session: 数据库会话
    :param obj: 待迁移的文件对象
    :param dest_policy: 目标存储策略
    :param task: 关联的任务记录
    """
    try:
        task.status = TaskStatus.RUNNING
        task.progress = 0
        task = await task.save(session)

        await migrate_single_file(session, obj, dest_policy)

        task.status = TaskStatus.COMPLETED
        task.progress = 100
        await task.save(session)
    except Exception as e:
        l.error(f"文件迁移任务失败: {obj.id}: {e}")
        task.status = TaskStatus.ERROR
        task.error = str(e)[:500]
        await task.save(session)


async def migrate_directory_files(
        session: AsyncSession,
        folder: Object,
        dest_policy: Policy,
        task: Task,
) -> None:
    """
    迁移目录下所有文件到目标存储策略

    递归遍历目录树，将所有文件迁移到目标策略。
    子目录的 policy_id 同步更新。
    任务进度按文件数比例更新。

    :param session: 数据库会话
    :param folder: 目录对象
    :param dest_policy: 目标存储策略
    :param task: 关联的任务记录
    """
    try:
        task.status = TaskStatus.RUNNING
        task.progress = 0
        task = await task.save(session)

        # 收集所有需要迁移的文件
        files_to_migrate: list[Object] = []
        folders_to_update: list[Object] = []
        await _collect_objects_recursive(session, folder, files_to_migrate, folders_to_update)

        total = len(files_to_migrate)
        migrated = 0
        errors: list[str] = []

        for file_obj in files_to_migrate:
            try:
                await migrate_single_file(session, file_obj, dest_policy)
                migrated += 1
            except Exception as e:
                error_msg = f"{file_obj.name}: {e}"
                l.error(f"迁移文件失败: {error_msg}")
                errors.append(error_msg)

            # 更新进度
            if total > 0:
                task.progress = min(99, int(migrated / total * 100))
                task = await task.save(session)

        # 更新所有子目录的 policy_id
        for sub_folder in folders_to_update:
            sub_folder.policy_id = dest_policy.id
            await sub_folder.save(session)

        # 完成任务
        if errors:
            task.status = TaskStatus.ERROR
            task.error = f"部分文件迁移失败 ({len(errors)}/{total}): " + "; ".join(errors[:5])
        else:
            task.status = TaskStatus.COMPLETED

        task.progress = 100
        await task.save(session)

        l.info(
            f"目录迁移完成: {folder.name} ({folder.id}), "
            f"成功 {migrated}/{total}, 错误 {len(errors)}"
        )
    except Exception as e:
        l.error(f"目录迁移任务失败: {folder.id}: {e}")
        task.status = TaskStatus.ERROR
        task.error = str(e)[:500]
        await task.save(session)


async def _collect_objects_recursive(
        session: AsyncSession,
        folder: Object,
        files: list[Object],
        folders: list[Object],
) -> None:
    """
    递归收集目录下所有文件和子目录

    :param session: 数据库会话
    :param folder: 当前目录
    :param files: 文件列表（输出）
    :param folders: 子目录列表（输出）
    """
    children: list[Object] = await Object.get_children(session, folder.owner_id, folder.id)

    for child in children:
        if child.type == ObjectType.FILE:
            files.append(child)
        elif child.type == ObjectType.FOLDER:
            folders.append(child)
            await _collect_objects_recursive(session, child, files, folders)
