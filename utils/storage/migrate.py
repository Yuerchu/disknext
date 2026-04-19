"""
存储策略迁移工具

提供带任务跟踪的跨存储策略文件迁移功能：
- 单文件迁移（带任务状态更新）
- 目录批量迁移（带进度更新）

底层迁移逻辑由 File.migrate_to_policy() 实现。
"""
from loguru import logger as l
from sqlmodel.ext.asyncio.session import AsyncSession

from sqlmodels.file import File, FileType
from sqlmodels.policy import Policy
from sqlmodels.task import Task, TaskStatus


async def migrate_file_with_task(
        session: AsyncSession,
        obj: File,
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

        await obj.migrate_to_policy(session, dest_policy)

        task.status = TaskStatus.COMPLETED
        task.progress = 100
        task = await task.save(session)
    except Exception as e:
        l.error(f"文件迁移任务失败: {obj.id}: {e}")
        task.status = TaskStatus.ERROR
        task.error = str(e)[:500]
        task = await task.save(session)


async def migrate_directory_files(
        session: AsyncSession,
        folder: File,
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
        files_to_migrate: list[File] = []
        folders_to_update: list[File] = []
        await _collect_objects_recursive(session, folder, files_to_migrate, folders_to_update)

        total = len(files_to_migrate)
        migrated = 0
        errors: list[str] = []

        for file_obj in files_to_migrate:
            try:
                await file_obj.migrate_to_policy(session, dest_policy)
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
            sub_folder = await sub_folder.save(session)

        # 完成任务
        if errors:
            task.status = TaskStatus.ERROR
            task.error = f"部分文件迁移失败 ({len(errors)}/{total}): " + "; ".join(errors[:5])
        else:
            task.status = TaskStatus.COMPLETED

        task.progress = 100
        task = await task.save(session)

        l.info(
            f"目录迁移完成: {folder.name} ({folder.id}), "
            f"成功 {migrated}/{total}, 错误 {len(errors)}"
        )
    except Exception as e:
        l.error(f"目录迁移任务失败: {folder.id}: {e}")
        task.status = TaskStatus.ERROR
        task.error = str(e)[:500]
        task = await task.save(session)


async def _collect_objects_recursive(
        session: AsyncSession,
        folder: File,
        files: list[File],
        folders: list[File],
) -> None:
    """
    递归收集目录下所有文件和子目录

    :param session: 数据库会话
    :param folder: 当前目录
    :param files: 文件列表（输出）
    :param folders: 子目录列表（输出）
    """
    children: list[File] = await File.get_children(session, folder.owner_id, folder.id)

    for child in children:
        if child.type == FileType.FILE:
            files.append(child)
        elif child.type == FileType.FOLDER:
            folders.append(child)
            await _collect_objects_recursive(session, child, files, folders)
