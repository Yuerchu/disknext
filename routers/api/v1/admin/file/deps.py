from datetime import datetime
from uuid import UUID

from sqlmodel import col, update as sql_update
from sqlmodel.ext.asyncio.session import AsyncSession

from sqlmodels import Entry


async def set_ban_recursive(
    session: AsyncSession,
    obj: Entry,
    ban: bool,
    admin_id: UUID,
    reason: str | None,
) -> int:
    """
    递归设置封禁状态，返回受影响对象数量。

    BFS 收集所有后代 ID，然后批量 UPDATE。

    :param session: 数据库会话
    :param obj: 要封禁/解禁的对象
    :param ban: True=封禁, False=解禁
    :param admin_id: 管理员UUID
    :param reason: 封禁原因
    :return: 受影响的对象数量
    """
    # BFS 收集所有后代 ID（包含自身）
    all_ids: list[UUID] = [obj.id]
    if obj.type == EntryType.FOLDER:
        queue: list[UUID] = [obj.id]
        while queue:
            parent_id = queue.pop(0)
            children = await Entry.get(
                session, Entry.parent_id == parent_id, fetch_mode="all",
            )
            for child in children:
                all_ids.append(child.id)
                if child.type == EntryType.FOLDER:
                    queue.append(child.id)

    # 批量 UPDATE
    if ban:
        now = datetime.now()
        stmt = sql_update(Entry).where(col(Entry.id).in_(all_ids)).values(
            is_banned=True, banned_at=now, banned_by=admin_id, ban_reason=reason,
        )
    else:
        stmt = sql_update(Entry).where(col(Entry.id).in_(all_ids)).values(
            is_banned=False, banned_at=None, banned_by=None, ban_reason=None,
        )
    _ = await session.exec(stmt)
    await session.commit()
    return len(all_ids)
