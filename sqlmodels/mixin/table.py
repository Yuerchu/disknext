"""
表基类 Mixin

提供 TableBaseMixin、UUIDTableBaseMixin 和 TableViewRequest。
这些类实际上是 Mixin，为 SQLModel 模型提供 CRUD 操作和时间戳字段。

依赖关系：
    base/sqlmodel_base.py  ← 最底层
            ↓
    mixin/polymorphic.py  ← 定义 PolymorphicBaseMixin
            ↓
    mixin/table.py  ← 当前文件，导入 PolymorphicBaseMixin
            ↓
    base/__init__.py  ← 从 mixin 重新导出（保持向后兼容）

维护须知：
    增删功能时必须更新 __version__ 字段（遵循语义化版本）

版本历史：
    0.1.0 - delete() 方法支持条件删除（condition 参数）
"""
__version__ = "0.1.0"
import uuid
from datetime import datetime
from typing import TypeVar, Literal, override, Any, ClassVar, Generic

# TODO(ListResponse泛型问题): SQLModel泛型类型JSON Schema生成bug
# 已知问题: https://github.com/fastapi/sqlmodel/discussions/1002
# 修复PR: https://github.com/fastapi/sqlmodel/pull/1275 (尚未合并)
# 现象: SQLModel + Generic[T] 的 __pydantic_generic_metadata__ = {origin: None, args: ()}
#       导致OpenAPI schema中泛型字段显示为{}而非正确的$ref
# 当前方案: ListResponse继承BaseModel而非SQLModel (Discussion #1002推荐的workaround)
# 未来: PR #1275合并后可改回继承SQLModelBase
from pydantic import BaseModel, ConfigDict
from fastapi import HTTPException
from sqlalchemy import DateTime, BinaryExpression, ClauseElement, desc, asc, func, distinct, delete as sql_delete, inspect
from sqlalchemy.orm import selectinload, Relationship, with_polymorphic
from sqlalchemy.orm.exc import StaleDataError
from sqlmodel import Field, select

from .optimistic_lock import OptimisticLockError
from sqlmodel.ext.asyncio.session import AsyncSession
from sqlalchemy.sql._typing import _OnClauseArgument
from sqlalchemy.ext.asyncio import AsyncAttrs
from sqlmodel.main import RelationshipInfo

from .polymorphic import PolymorphicBaseMixin
from sqlmodels.base.sqlmodel_base import SQLModelBase

# Type variables for generic type hints, improving code completion and analysis.
T = TypeVar("T", bound="TableBaseMixin")
M = TypeVar("M", bound="SQLModelBase")
ItemT = TypeVar("ItemT")


class ListResponse(BaseModel, Generic[ItemT]):
    """
    泛型分页响应

    用于所有LIST端点的标准化响应格式，包含记录总数和项目列表。
    与 TableBaseMixin.get_with_count() 配合使用。

    使用示例：
        ```python
        @router.get("", response_model=ListResponse[CharacterInfoResponse])
        async def list_characters(...) -> ListResponse[Character]:
            return await Character.get_with_count(session, table_view=table_view)
        ```

    Attributes:
        count: 符合条件的记录总数（用于分页计算）
        items: 当前页的记录列表

    Note:
        继承BaseModel而非SQLModelBase，因为SQLModel的metaclass与Generic冲突。
        详见文件顶部TODO注释。
    """
    # 与SQLModelBase保持一致的配置
    model_config = ConfigDict(use_attribute_docstrings=True)

    count: int
    """符合条件的记录总数"""

    items: list[ItemT]
    """当前页的记录列表"""


# Lambda functions to get the current time, used as default factories in model fields.
now = lambda: datetime.now()
now_date = lambda: datetime.now().date()


# ==================== 查询参数请求类 ====================

class TimeFilterRequest(SQLModelBase):
    """
    时间筛选请求参数

    用于 count() 等只需要时间筛选的场景。
    纯数据类，只负责参数校验和携带，SQL子句构建由 TableBaseMixin 负责。

    Raises:
        ValueError: 时间范围无效
    """
    created_after_datetime: datetime | None = None
    """创建时间起始筛选（created_at >= datetime），如果为None则不限制"""

    created_before_datetime: datetime | None = None
    """创建时间结束筛选（created_at < datetime），如果为None则不限制"""

    updated_after_datetime: datetime | None = None
    """更新时间起始筛选（updated_at >= datetime），如果为None则不限制"""

    updated_before_datetime: datetime | None = None
    """更新时间结束筛选（updated_at < datetime），如果为None则不限制"""

    def model_post_init(self, __context: Any) -> None:
        """
        验证时间范围有效性

        验证规则：
        1. 同类型：after 必须小于 before
        2. 跨类型：created_after 不能大于 updated_before（记录不可能在创建前被更新）
        """
        # 同类型矛盾验证
        if self.created_after_datetime and self.created_before_datetime:
            if self.created_after_datetime >= self.created_before_datetime:
                raise ValueError("created_after_datetime 必须小于 created_before_datetime")
        if self.updated_after_datetime and self.updated_before_datetime:
            if self.updated_after_datetime >= self.updated_before_datetime:
                raise ValueError("updated_after_datetime 必须小于 updated_before_datetime")

        # 跨类型矛盾验证：created_after >= updated_before 意味着要求创建时间晚于或等于更新时间上界，逻辑矛盾
        if self.created_after_datetime and self.updated_before_datetime:
            if self.created_after_datetime >= self.updated_before_datetime:
                raise ValueError(
                    "created_after_datetime 不能大于或等于 updated_before_datetime"
                    "（记录的更新时间不可能早于或等于创建时间）"
                )


class PaginationRequest(SQLModelBase):
    """
    分页排序请求参数

    用于需要分页和排序的场景。
    纯数据类，只负责携带参数，SQL子句构建由 TableBaseMixin 负责。
    """
    offset: int | None = Field(default=0, ge=0)
    """偏移量（跳过前N条记录），必须为非负整数"""

    limit: int | None = Field(default=50, le=100)
    """每页数量（返回最多N条记录），默认50，最大100"""

    desc: bool | None = True
    """是否降序排序（True: 降序, False: 升序）"""

    order: Literal["created_at", "updated_at"] | None = "created_at"
    """排序字段（created_at: 创建时间, updated_at: 更新时间）"""


class TableViewRequest(TimeFilterRequest, PaginationRequest):
    """
    表格视图请求参数（分页、排序和时间筛选）

    组合继承 TimeFilterRequest 和 PaginationRequest，用于 get() 等需要完整查询参数的场景。
    纯数据类，SQL子句构建由 TableBaseMixin 负责。

    使用示例：
        ```python
        # 在端点中使用依赖注入
        @router.get("/list")
        async def list_items(
            session: SessionDep,
            table_view: TableViewRequestDep
        ):
            items = await Item.get(
                session,
                fetch_mode="all",
                table_view=table_view
            )
            return items

        # 直接使用
        table_view = TableViewRequest(offset=0, limit=20, desc=True, order="created_at")
        items = await Item.get(session, fetch_mode="all", table_view=table_view)
        ```
    """
    pass


# ==================== TableBaseMixin ====================

class TableBaseMixin(AsyncAttrs):
    """
    一个异步 CRUD 操作的基础模型类 Mixin.

    此类必须搭配SQLModelBase使用

    此类为所有继承它的 SQLModel 模型提供了通用的数据库操作方法，
    例如 add, save, update, delete, 和 get. 它还包括自动管理
    的 `created_at` 和 `updated_at` 时间戳字段.

    Attributes:
        id (int | None): 整数主键, 自动递增.
        created_at (datetime): 记录创建时的时间戳, 自动设置.
        updated_at (datetime): 记录每次更新时的时间戳, 自动更新.
    """
    _has_table_mixin: ClassVar[bool] = True
    """标记此类继承了表混入类的内部属性"""

    def __init_subclass__(cls, **kwargs):
        """
        接受并传递子类定义时的关键字参数

        这允许元类 __DeclarativeMeta 处理的参数（如 table_args）
        能够正确传递，而不会在 __init_subclass__ 阶段报错。
        """
        super().__init_subclass__(**kwargs)

    id: int | None = Field(default=None, primary_key=True)

    created_at: datetime = Field(default_factory=now)
    updated_at: datetime = Field(
        sa_type=DateTime,
        sa_column_kwargs={'default': now, 'onupdate': now},
        default_factory=now
    )

    @classmethod
    async def add(cls: type[T], session: AsyncSession, instances: T | list[T], refresh: bool = True) -> T | list[T]:
        """
        向数据库中添加一个新的或多个新的记录.

        这个类方法可以接受单个模型实例或一个实例列表，并将它们
        一次性提交到数据库中。执行后，可以选择性地刷新这些实例以获取
        数据库生成的值（例如，自动递增的 ID）.

        Args:
            session (AsyncSession): 用于数据库操作的异步会话对象.
            instances (T | list[T]): 要添加的单个模型实例或模型实例列表.
            refresh (bool): 如果为 True, 将在提交后刷新实例以同步数据库状态. 默认为 True.

        Returns:
            T | list[T]: 已添加并（可选地）刷新的一个或多个模型实例.

        Usage:
            item1 = Item(name="Apple")
            item2 = Item(name="Banana")

            # 添加多个实例
            added_items = await Item.add(session, [item1, item2])

            # 添加单个实例
            item3 = Item(name="Cherry")
            added_item = await Item.add(session, item3)
        """
        is_list = False
        if isinstance(instances, list):
            is_list = True
            session.add_all(instances)
        else:
            session.add(instances)

        await session.commit()

        if refresh:
            if is_list:
                for instance in instances:
                    await session.refresh(instance)
            else:
                await session.refresh(instances)

        return instances

    async def save(
            self: T,
            session: AsyncSession,
            load: RelationshipInfo | list[RelationshipInfo] | None = None,
            refresh: bool = True,
            commit: bool = True,
            jti_subclasses: list[type[PolymorphicBaseMixin]] | Literal['all'] | None = None,
            optimistic_retry_count: int = 0,
    ) -> T:
        """
        保存（插入或更新）当前模型实例到数据库.

        这是一个实例方法，它将当前对象添加到会话中并提交更改。
        可以用于创建新记录或更新现有记录。还可以选择在保存后
        预加载（eager load）一个关联关系.

        **重要**：调用此方法后，session中的所有对象都会过期（expired）。
        如果需要继续使用该对象，必须使用返回值：

        ```python
        # ✅ 正确：需要返回值时
        client = await client.save(session)
        return client

        # ✅ 正确：不需要返回值时，指定 refresh=False 节省性能
        await client.save(session, refresh=False)

        # ✅ 正确：批量操作时延迟提交
        for item in items:
            item = await item.save(session, commit=False)
        await session.commit()

        # ✅ 正确：保存后需要访问多态关系时
        tool_set = await tool_set.save(session, load=ToolSet.tools, jti_subclasses='all')
        return tool_set  # tools 关系已正确加载子类数据

        # ✅ 正确：启用乐观锁自动重试
        order = await order.save(session, optimistic_retry_count=3)

        # ❌ 错误：需要返回值但未使用
        await client.save(session)
        return client  # client 对象已过期
        ```

        Args:
            session (AsyncSession): 用于数据库操作的异步会话对象.
            load (Relationship | None): 可选的，指定在保存和刷新后要预加载的关联属性.
                                          例如 `User.posts`.
            refresh (bool): 是否在保存后刷新对象。如果不需要使用返回值，
                           设为 False 可节省一次数据库查询。默认为 True.
            commit (bool): 是否在保存后提交事务。如果为 False，只会 flush 获取 ID
                          但不提交，适用于批量操作场景。默认为 True.
            jti_subclasses: 多态子类加载选项，需要与 load 参数配合使用。
                - list[type[PolymorphicBaseMixin]]: 指定要加载的子类列表
                - 'all': 两阶段查询，只加载实际关联的子类
                - None（默认）: 不使用多态加载
            optimistic_retry_count (int): 乐观锁冲突时的自动重试次数。默认为 0（不重试）。
                重试时会重新查询最新数据，将当前修改合并后再次保存。

        Returns:
            T: 如果 refresh=True，返回已刷新的模型实例；否则返回未刷新的 self.

        Raises:
            OptimisticLockError: 如果启用了乐观锁且版本号不匹配，且重试次数已耗尽
        """
        cls = type(self)
        instance = self
        retries_remaining = optimistic_retry_count
        current_data: dict[str, Any] | None = None  # 延迟计算，仅在需要重试时

        while True:
            session.add(instance)
            try:
                if commit:
                    await session.commit()
                else:
                    await session.flush()
                break  # 成功，退出循环
            except StaleDataError as e:
                await session.rollback()
                if retries_remaining <= 0:
                    raise OptimisticLockError(
                        message=f"{cls.__name__} 乐观锁冲突：记录已被其他事务修改",
                        model_class=cls.__name__,
                        record_id=str(getattr(instance, 'id', None)),
                        expected_version=getattr(instance, 'version', None),
                        original_error=e,
                    ) from e

                # 失败后重试：重新查询最新数据并合并修改
                retries_remaining -= 1
                if current_data is None:
                    current_data = self.model_dump(exclude={'id', 'version', 'created_at', 'updated_at'})

                fresh = await cls.get(session, cls.id == self.id)
                if fresh is None:
                    raise OptimisticLockError(
                        message=f"{cls.__name__} 重试失败：记录已被删除",
                        model_class=cls.__name__,
                        record_id=str(getattr(self, 'id', None)),
                        original_error=e,
                    ) from e

                for key, value in current_data.items():
                    if hasattr(fresh, key):
                        setattr(fresh, key, value)
                instance = fresh

        if not refresh:
            return instance

        if load is not None:
            await session.refresh(instance)
            return await cls.get(session, cls.id == instance.id, load=load, jti_subclasses=jti_subclasses)
        else:
            await session.refresh(instance)
            return instance

    async def update(
            self: T,
            session: AsyncSession,
            other: M,
            extra_data: dict[str, Any] | None = None,
            exclude_unset: bool = True,
            exclude: set[str] | None = None,
            load: RelationshipInfo | list[RelationshipInfo] | None = None,
            refresh: bool = True,
            commit: bool = True,
            jti_subclasses: list[type[PolymorphicBaseMixin]] | Literal['all'] | None = None,
            optimistic_retry_count: int = 0,
    ) -> T:
        """
        使用另一个模型实例或字典中的数据来更新当前实例.

        此方法将 `other` 对象中的数据合并到当前实例中。默认情况下，
        它只会更新 `other` 中被显式设置的字段.

        **重要**：调用此方法后，session中的所有对象都会过期（expired）。
        如果需要继续使用该对象，必须使用返回值：

        ```python
        # ✅ 正确：需要返回值时
        client = await client.update(session, update_data)
        return client

        # ✅ 正确：需要返回值且需要加载关系时
        user = await user.update(session, update_data, load=User.permission)
        return user

        # ✅ 正确：更新后需要访问多态关系时
        tool_set = await tool_set.update(session, data, load=ToolSet.tools, jti_subclasses='all')
        return tool_set  # tools 关系已正确加载子类数据

        # ✅ 正确：不需要返回值时，指定 refresh=False 节省性能
        await client.update(session, update_data, refresh=False)

        # ✅ 正确：批量操作时延迟提交
        for item in items:
            item = await item.update(session, data, commit=False)
        await session.commit()

        # ✅ 正确：启用乐观锁自动重试
        order = await order.update(session, update_data, optimistic_retry_count=3)

        # ❌ 错误：需要返回值但未使用
        await client.update(session, update_data)
        return client  # client 对象已过期
        ```

        Args:
            session (AsyncSession): 用于数据库操作的异步会话对象.
            other (M): 一个 SQLModel 或 Pydantic 模型实例，其数据将用于更新当前实例.
            extra_data (dict, optional): 一个额外的字典，用于更新当前实例的特定字段.
            exclude_unset (bool): 如果为 True, `other` 对象中未设置（即值为 None 或未提供）
                                  的字段将被忽略. 默认为 True.
            exclude (set[str] | None): 要从更新中排除的字段名集合。例如 {'permission'}.
            load (RelationshipInfo | None): 可选的，指定在更新和刷新后要预加载的关联属性.
                                             例如 `User.permission`.
            refresh (bool): 是否在更新后刷新对象。如果不需要使用返回值，
                           设为 False 可节省一次数据库查询。默认为 True.
            commit (bool): 是否在更新后提交事务。如果为 False，只会 flush
                          但不提交，适用于批量操作场景。默认为 True.
            jti_subclasses: 多态子类加载选项，需要与 load 参数配合使用。
                - list[type[PolymorphicBaseMixin]]: 指定要加载的子类列表
                - 'all': 两阶段查询，只加载实际关联的子类
                - None（默认）: 不使用多态加载
            optimistic_retry_count (int): 乐观锁冲突时的自动重试次数。默认为 0（不重试）。
                重试时会重新查询最新数据，将 other 的更新重新应用后再次保存。

        Returns:
            T: 如果 refresh=True，返回已刷新的模型实例；否则返回未刷新的 self.

        Raises:
            OptimisticLockError: 如果启用了乐观锁且版本号不匹配，且重试次数已耗尽
        """
        cls = type(self)
        update_data = other.model_dump(exclude_unset=exclude_unset, exclude=exclude)
        instance = self
        retries_remaining = optimistic_retry_count

        while True:
            instance.sqlmodel_update(update_data, update=extra_data)
            session.add(instance)

            try:
                if commit:
                    await session.commit()
                else:
                    await session.flush()
                break  # 成功，退出循环
            except StaleDataError as e:
                await session.rollback()
                if retries_remaining <= 0:
                    raise OptimisticLockError(
                        message=f"{cls.__name__} 乐观锁冲突：记录已被其他事务修改",
                        model_class=cls.__name__,
                        record_id=str(getattr(instance, 'id', None)),
                        expected_version=getattr(instance, 'version', None),
                        original_error=e,
                    ) from e

                # 失败后重试：重新查询最新数据并重新应用更新
                retries_remaining -= 1
                fresh = await cls.get(session, cls.id == self.id)
                if fresh is None:
                    raise OptimisticLockError(
                        message=f"{cls.__name__} 重试失败：记录已被删除",
                        model_class=cls.__name__,
                        record_id=str(getattr(self, 'id', None)),
                        original_error=e,
                    ) from e
                instance = fresh

        if not refresh:
            return instance

        if load is not None:
            await session.refresh(instance)
            return await cls.get(session, cls.id == instance.id, load=load, jti_subclasses=jti_subclasses)
        else:
            await session.refresh(instance)
            return instance

    @classmethod
    async def delete(
            cls: type[T],
            session: AsyncSession,
            instances: T | list[T] | None = None,
            *,
            condition: BinaryExpression | ClauseElement | None = None,
            commit: bool = True,
    ) -> int:
        """
        从数据库中删除记录，支持实例删除和条件删除两种模式。

        Args:
            session: 用于数据库操作的异步会话对象
            instances: 要删除的单个模型实例或模型实例列表（实例删除模式）
            condition: WHERE 条件表达式（条件删除模式，直接执行 SQL DELETE）
            commit: 是否在删除后提交事务。默认为 True

        Returns:
            删除的记录数（条件删除模式返回实际删除数，实例删除模式返回实例数）

        Raises:
            ValueError: 同时提供 instances 和 condition，或两者都未提供

        Usage:
            # 实例删除模式
            item = await Item.get(session, Item.id == 1)
            if item:
                await Item.delete(session, item)

            items = await Item.get(session, Item.name.in_(["A", "B"]), fetch_mode="all")
            if items:
                await Item.delete(session, items)

            # 条件删除模式（高效批量删除，不加载实例到内存）
            deleted_count = await Item.delete(
                session,
                condition=(Item.user_id == user_id) & (Item.status == "expired"),
            )
        """
        if instances is not None and condition is not None:
            raise ValueError("不能同时提供 instances 和 condition 参数")
        if instances is None and condition is None:
            raise ValueError("必须提供 instances 或 condition 参数之一")

        deleted_count = 0

        if condition is not None:
            # 条件删除模式：直接执行 SQL DELETE
            stmt = sql_delete(cls).where(condition)
            result = await session.execute(stmt)
            deleted_count = result.rowcount
        else:
            # 实例删除模式
            if isinstance(instances, list):
                for instance in instances:
                    await session.delete(instance)
                deleted_count = len(instances)
            else:
                await session.delete(instances)
                deleted_count = 1

        if commit:
            await session.commit()

        return deleted_count

    @classmethod
    def _build_time_filters(
            cls: type[T],
            created_before_datetime: datetime | None = None,
            created_after_datetime: datetime | None = None,
            updated_before_datetime: datetime | None = None,
            updated_after_datetime: datetime | None = None,
    ) -> list[BinaryExpression]:
        """
        构建时间筛选条件列表

        Args:
            created_before_datetime: 筛选 created_at < datetime 的记录
            created_after_datetime: 筛选 created_at >= datetime 的记录
            updated_before_datetime: 筛选 updated_at < datetime 的记录
            updated_after_datetime: 筛选 updated_at >= datetime 的记录

        Returns:
            BinaryExpression 条件列表
        """
        filters: list[BinaryExpression] = []
        if created_after_datetime is not None:
            filters.append(cls.created_at >= created_after_datetime)
        if created_before_datetime is not None:
            filters.append(cls.created_at < created_before_datetime)
        if updated_after_datetime is not None:
            filters.append(cls.updated_at >= updated_after_datetime)
        if updated_before_datetime is not None:
            filters.append(cls.updated_at < updated_before_datetime)
        return filters

    @classmethod
    async def get(
            cls: type[T],
            session: AsyncSession,
            condition: BinaryExpression | ClauseElement | None = None,
            *,
            offset: int | None = None,
            limit: int | None = None,
            fetch_mode: Literal["one", "first", "all"] = "first",
            join: type[T] | tuple[type[T], _OnClauseArgument] | None = None,
            options: list | None = None,
            load: RelationshipInfo | list[RelationshipInfo] | None = None,
            order_by: list[ClauseElement] | None = None,
            filter: BinaryExpression | ClauseElement | None = None,
            with_for_update: bool = False,
            table_view: TableViewRequest | None = None,
            jti_subclasses: list[type[PolymorphicBaseMixin]] | Literal['all'] | None = None,
            populate_existing: bool = False,
            created_before_datetime: datetime | None = None,
            created_after_datetime: datetime | None = None,
            updated_before_datetime: datetime | None = None,
            updated_after_datetime: datetime | None = None,
    ) -> T | list[T] | None:
        """
        根据指定的条件异步地从数据库中获取一个或多个模型实例.

        这是一个功能强大的通用查询方法，支持过滤、排序、分页、连接查询和关联关系预加载.

        Args:
            session (AsyncSession): 用于数据库操作的异步会话对象.
            condition (BinaryExpression | ClauseElement | None): 主要的查询过滤条件,
                                                                 例如 `User.id == 1`。
                                                                 当为 `None` 时，表示无条件查询（查询所有记录）。
            offset (int | None): 查询结果的起始偏移量, 用于分页.
            limit (int | None): 返回记录的最大数量, 用于分页.
            fetch_mode (Literal["one", "first", "all"]):
                - "one": 获取唯一的一条记录. 如果找不到或找到多条，会引发异常.
                - "first": 获取查询结果的第一条记录. 如果找不到，返回 `None`.
                - "all": 获取所有匹配的记录，返回一个列表.
                默认为 "first".
            join (type[T] | tuple[type[T], _OnClauseArgument] | None):
                要 JOIN 的模型类或一个包含模型类和 ON 子句的元组.
                例如 `User` 或 `(Profile, User.id == Profile.user_id)`.
            options (list | None): SQLAlchemy 查询选项列表, 通常用于预加载关联数据,
                                   例如 `[selectinload(User.posts)]`.
            load (Relationship | list[Relationship] | None): `selectinload` 的快捷方式，用于预加载关联关系.
                                                可以是单个关系或关系列表。支持嵌套关系预加载：
                                                当传入多个关系时，会自动检测依赖关系并构建链式 selectinload。
                                                例如 `[NodeGroupNode.element_links, NodeGroupElementLink.node]`
                                                会自动构建 `selectinload(element_links).selectinload(node)`。
            order_by (list[ClauseElement] | None): 用于排序的排序列或表达式的列表.
                                                   例如 `[User.name.asc(), User.created_at.desc()]`.
            filter (BinaryExpression | ClauseElement | None): 附加的过滤条件.

            with_for_update (bool): 如果为 True, 在查询中使用 `FOR UPDATE` 锁定选定的行. 默认为 False.

            table_view (TableViewRequest | None): TableViewRequest对象，如果提供则自动处理分页、排序和时间筛选。
                                                  会覆盖offset、limit、order_by及时间筛选参数。
                                                  这是推荐的分页排序方式，统一了所有LIST端点的参数格式。

            jti_subclasses: 多态子类加载选项，需要与 load 参数配合使用。
                - list[type[PolymorphicBaseMixin]]: 指定要加载的子类列表
                - 'all': 两阶段查询，只加载实际关联的子类（对于 > 10 个子类的场景有明显性能收益）
                - None（默认）: 不使用多态加载

            populate_existing (bool): 如果为 True，强制用数据库数据覆盖 session 中已存在的对象（identity map）。
                用于批量刷新对象，避免循环调用 session.refresh() 导致的 N 次查询。
                注意：只刷新标量字段，不影响运行时属性（_开头的属性）。
                对于 STI（单表继承）对象，推荐按子类分组查询以包含子类字段。默认为 False。

            created_before_datetime (datetime | None): 筛选 created_at < datetime 的记录
            created_after_datetime (datetime | None): 筛选 created_at >= datetime 的记录
            updated_before_datetime (datetime | None): 筛选 updated_at < datetime 的记录
            updated_after_datetime (datetime | None): 筛选 updated_at >= datetime 的记录

        Returns:
            T | list[T] | None: 根据 `fetch_mode` 的设置，返回单个实例、实例列表或 `None`.

        Raises:
            ValueError: 如果提供了无效的 `fetch_mode` 值，或 jti_subclasses 未与 load 配合使用.

        Examples:
            # 使用table_view参数（推荐）
            users = await User.get(session, fetch_mode="all", table_view=table_view_args)

            # 传统方式（向后兼容）
            users = await User.get(session, fetch_mode="all", offset=0, limit=20, order_by=[desc(User.created_at)])

            # 使用多态加载（加载联表继承的子类数据）
            tool_set = await ToolSet.get(
                session,
                ToolSet.id == tool_set_id,
                load=ToolSet.tools,
                jti_subclasses='all'  # 只加载实际关联的子类
            )
        """
        # 参数验证：jti_subclasses 需要与 load 配合使用
        if jti_subclasses is not None and load is None:
            raise ValueError(
                "jti_subclasses 参数需要与 load 参数配合使用，"
                "请同时指定要加载的关系"
            )

        # 如果提供table_view，作为默认值使用（单独传入的参数优先级更高）
        if table_view:
            # 处理时间筛选（TimeFilterRequest 及其子类）
            if isinstance(table_view, TimeFilterRequest):
                if created_after_datetime is None and table_view.created_after_datetime is not None:
                    created_after_datetime = table_view.created_after_datetime
                if created_before_datetime is None and table_view.created_before_datetime is not None:
                    created_before_datetime = table_view.created_before_datetime
                if updated_after_datetime is None and table_view.updated_after_datetime is not None:
                    updated_after_datetime = table_view.updated_after_datetime
                if updated_before_datetime is None and table_view.updated_before_datetime is not None:
                    updated_before_datetime = table_view.updated_before_datetime
            # 处理分页排序（PaginationRequest 及其子类，包括 TableViewRequest）
            if isinstance(table_view, PaginationRequest):
                if offset is None:
                    offset = table_view.offset
                if limit is None:
                    limit = table_view.limit
                # 仅在未显式传入order_by时，从table_view构建排序子句
                if order_by is None:
                    order_column = cls.created_at if table_view.order == "created_at" else cls.updated_at
                    order_by = [desc(order_column) if table_view.desc else asc(order_column)]

        # 对于多态基类，使用 with_polymorphic 预加载所有子类的列
        # 这避免了在响应序列化时的延迟加载问题（MissingGreenlet 错误）
        polymorphic_cls = None  # 保存多态实体，用于子类关系预加载
        is_polymorphic = issubclass(cls, PolymorphicBaseMixin)
        is_jti = is_polymorphic and cls._is_joined_table_inheritance()
        is_sti = is_polymorphic and not cls._is_joined_table_inheritance()

        # JTI 模式：总是使用 with_polymorphic（避免 N+1 查询）
        # STI 模式：不使用 with_polymorphic（批量刷新时请按子类分组查询）
        if is_jti:
            # '*' 表示加载所有子类
            polymorphic_cls = with_polymorphic(cls, '*')
            statement = select(polymorphic_cls)
        else:
            statement = select(cls)

        # 对于 STI（单表继承）子类，自动添加多态过滤条件
        # SQLAlchemy/SQLModel 在 STI 模式下不会自动添加 WHERE discriminator = 'identity' 过滤
        # 这是已知行为，参考:
        # - https://github.com/sqlalchemy/sqlalchemy/issues/5018 (bulk operations 不自动添加多态过滤)
        # - https://github.com/fastapi/sqlmodel/issues/488 (SQLModel STI 支持不完整)
        # 社区最佳实践是显式添加多态过滤条件
        if issubclass(cls, PolymorphicBaseMixin) and not cls._is_joined_table_inheritance():
            mapper = inspect(cls)
            # 检查是否有 polymorphic_identity 且不是抽象类
            if mapper.polymorphic_identity is not None and not mapper.polymorphic_abstract:
                poly_on = mapper.polymorphic_on
                if poly_on is not None:
                    statement = statement.where(poly_on == mapper.polymorphic_identity)

        if condition is not None:
            statement = statement.where(condition)

        # 应用时间筛选
        for time_filter in cls._build_time_filters(
            created_before_datetime, created_after_datetime,
            updated_before_datetime, updated_after_datetime
        ):
            statement = statement.where(time_filter)

        if join is not None:
            # 如果 join 是一个元组，解包它；否则直接使用
            if isinstance(join, tuple):
                statement = statement.join(*join)
            else:
                statement = statement.join(join)


        if options:
            statement = statement.options(*options)

        if load:
            # 标准化为列表
            load_list = load if isinstance(load, list) else [load]

            # 构建链式 selectinload（支持嵌套关系预加载）
            # 例如：load=[NodeGroupNode.element_links, NodeGroupElementLink.node]
            # 会构建：selectinload(element_links).selectinload(node)
            load_chains = cls._build_load_chains(load_list)

            # 处理多态加载（仅支持单链且只有一个关系）
            if jti_subclasses is not None:
                if len(load_chains) > 1 or len(load_chains[0]) > 1:
                    raise ValueError(
                        "jti_subclasses 仅支持单个关系（无嵌套链），请不要传入多个关系"
                    )
                single_load = load_chains[0][0]
                target_class = single_load.property.mapper.class_

                # 检查目标类是否继承自 PolymorphicBaseMixin
                if not issubclass(target_class, PolymorphicBaseMixin):
                    raise ValueError(
                        f"目标类 {target_class.__name__} 不是多态类，"
                        f"请确保其继承自 PolymorphicBaseMixin"
                    )

                if jti_subclasses == 'all':
                    # 两阶段查询：获取实际关联的多态类型
                    subclasses_to_load = await cls._resolve_polymorphic_subclasses(
                        session, condition, single_load, target_class
                    )
                else:
                    subclasses_to_load = jti_subclasses

                if subclasses_to_load:
                    # 关键：selectin_polymorphic 必须作为 selectinload 的链式子选项
                    # 参考: https://docs.sqlalchemy.org/en/20/orm/queryguide/relationships.html#polymorphic-eager-loading
                    statement = statement.options(
                        selectinload(single_load).selectin_polymorphic(subclasses_to_load)
                    )
                else:
                    statement = statement.options(selectinload(single_load))
            else:
                # 为每条链构建链式 selectinload
                for chain in load_chains:
                    # 获取第一个关系并检查是否需要通过多态实体访问
                    first_rel = chain[0]
                    first_rel_parent = first_rel.property.parent.class_

                    # 如果关系的 parent_class 是当前类的子类（不是 cls 本身），
                    # 且当前是多态查询，则需要通过 polymorphic_cls.SubclassName 访问
                    if (
                        polymorphic_cls is not None
                        and first_rel_parent is not cls
                        and issubclass(first_rel_parent, cls)
                    ):
                        # 通过多态实体访问子类的关系属性
                        # 例如：polymorphic_cls.NodeGroupNode.element_links
                        subclass_alias = getattr(polymorphic_cls, first_rel_parent.__name__)
                        rel_name = first_rel.key
                        first_rel_via_poly = getattr(subclass_alias, rel_name)
                        loader = selectinload(first_rel_via_poly)
                    else:
                        loader = selectinload(first_rel)

                    for rel in chain[1:]:
                        loader = loader.selectinload(rel)
                    statement = statement.options(loader)

        if order_by is not None:
            statement = statement.order_by(*order_by)

        if offset:
            statement = statement.offset(offset)

        if limit:
            statement = statement.limit(limit)

        if filter:
            statement = statement.filter(filter)

        if with_for_update:
            # 对于联表继承的多态模型，使用 FOR UPDATE OF <主表> 来避免 PostgreSQL 的限制
            # PostgreSQL 不支持在 LEFT OUTER JOIN 的可空侧使用 FOR UPDATE
            if issubclass(cls, PolymorphicBaseMixin):
                statement = statement.with_for_update(of=cls)
            else:
                statement = statement.with_for_update()

        if populate_existing:
            # 强制用数据库数据覆盖 identity map 中的对象
            # 用于批量刷新，避免循环 refresh() 的 N 次查询
            statement = statement.execution_options(populate_existing=True)

        result = await session.exec(statement)

        if fetch_mode == "one":
            return result.one()
        elif fetch_mode == "first":
            return result.first()
        elif fetch_mode == "all":
            return list(result.all())
        else:
            raise ValueError(f"无效的 fetch_mode: {fetch_mode}")

    @staticmethod
    def _build_load_chains(load_list: list[RelationshipInfo]) -> list[list[RelationshipInfo]]:
        """
        将关系列表构建为链式加载结构

        自动检测关系之间的依赖关系，构建嵌套预加载链。
        例如：[NodeGroupNode.element_links, NodeGroupElementLink.node]
        会构建：[[element_links, node]]（一条链）

        算法：
        1. 获取每个关系的 parent class 和 target class
        2. 如果关系 B 的 parent class 等于关系 A 的 target class，则 B 链在 A 后面
        3. 独立的关系各自成为一条链

        Args:
            load_list: 关系属性列表

        Returns:
            链式关系列表，每条链是一个关系列表
        """
        if not load_list:
            return []

        # 构建关系信息：{关系: (parent_class, target_class)}
        rel_info: dict[RelationshipInfo, tuple[type, type]] = {}
        for rel in load_list:
            parent_class = rel.property.parent.class_
            target_class = rel.property.mapper.class_
            rel_info[rel] = (parent_class, target_class)

        # 构建依赖图：{关系: 其前置关系}
        predecessors: dict[RelationshipInfo, RelationshipInfo | None] = {rel: None for rel in load_list}
        for rel_b in load_list:
            parent_b, _ = rel_info[rel_b]
            for rel_a in load_list:
                if rel_a is rel_b:
                    continue
                _, target_a = rel_info[rel_a]
                # 如果 B 的 parent 精确等于 A 的 target，则 B 链在 A 后面
                # 使用精确匹配避免继承关系导致的误判（如 NodeGroupNode 是 CanvasNode 子类）
                if parent_b is target_a:
                    predecessors[rel_b] = rel_a
                    break

        # 找出所有链的起点（没有前置关系的）
        roots = [rel for rel, pred in predecessors.items() if pred is None]

        # 构建链
        chains: list[list[RelationshipInfo]] = []
        used: set[RelationshipInfo] = set()

        for root in roots:
            chain = [root]
            used.add(root)
            # 找后续节点
            current = root
            while True:
                # 找以 current 的 target 为 parent 的关系
                _, current_target = rel_info[current]
                next_rel = None
                for rel, (parent, _) in rel_info.items():
                    if rel not in used and parent is current_target:
                        next_rel = rel
                        break
                if next_rel is None:
                    break
                chain.append(next_rel)
                used.add(next_rel)
                current = next_rel
            chains.append(chain)

        return chains

    @classmethod
    async def _resolve_polymorphic_subclasses(
            cls: type[T],
            session: AsyncSession,
            condition: BinaryExpression | ClauseElement | None,
            load: RelationshipInfo,
            target_class: type[PolymorphicBaseMixin]
    ) -> list[type[PolymorphicBaseMixin]]:
        """
        查询实际关联的多态子类类型

        通过查询多态鉴别字段确定实际存在的子类类型，
        避免加载所有可能的子类表（对于 > 10 个子类的场景有明显收益）。

        :param session: 数据库会话
        :param condition: 主查询的条件
        :param load: 关系属性
        :param target_class: 多态基类
        :return: 实际关联的子类列表
        """
        # 获取多态鉴别字段（会抛出 ValueError 如果未配置）
        discriminator = target_class.get_polymorphic_discriminator()
        poly_name_col = getattr(target_class, discriminator)

        # 获取关系属性
        relationship_property = load.property

        # 构建查询获取实际的多态类型名称
        if relationship_property.secondary is not None:
            # 多对多关系：通过中间表查询
            secondary = relationship_property.secondary
            local_cols = list(relationship_property.local_columns)

            type_query = (
                select(distinct(poly_name_col))
                .select_from(target_class)
                .join(secondary)
                .where(secondary.c[local_cols[0].name].in_(
                    select(cls.id).where(condition) if condition is not None else select(cls.id)
                ))
            )
        else:
            # 多对一/一对多关系：通过外键查询
            # local_remote_pairs[0] = (local_fk_col, remote_pk_col)
            # 对于多对一：local 是当前类的外键，remote 是目标类的主键
            local_fk_col = relationship_property.local_remote_pairs[0][0]
            remote_pk_col = relationship_property.local_remote_pairs[0][1]
            type_query = (
                select(distinct(poly_name_col))
                .where(remote_pk_col.in_(
                    select(local_fk_col).where(condition) if condition is not None else select(local_fk_col)
                ))
            )

        type_result = await session.exec(type_query)
        poly_names = list(type_result.all())

        if not poly_names:
            return []

        # 映射到子类（包含所有层级的具体子类）
        identity_map = target_class.get_identity_to_class_map()
        return [identity_map[name] for name in poly_names if name in identity_map]

    @classmethod
    async def count(
            cls: type[T],
            session: AsyncSession,
            condition: BinaryExpression | ClauseElement | None = None,
            *,
            time_filter: TimeFilterRequest | None = None,
            created_before_datetime: datetime | None = None,
            created_after_datetime: datetime | None = None,
            updated_before_datetime: datetime | None = None,
            updated_after_datetime: datetime | None = None,
    ) -> int:
        """
        根据条件统计记录数量（支持时间筛选）

        使用数据库层面的 COUNT() 聚合函数，比 get() + len() 更高效。

        Args:
            session: 数据库会话
            condition: 查询条件，例如 `User.is_active == True`
            time_filter: TimeFilterRequest 对象（优先级更高）
            created_before_datetime: 筛选 created_at < datetime 的记录
            created_after_datetime: 筛选 created_at >= datetime 的记录
            updated_before_datetime: 筛选 updated_at < datetime 的记录
            updated_after_datetime: 筛选 updated_at >= datetime 的记录

        Returns:
            符合条件的记录数量

        Examples:
            # 统计所有用户
            total = await User.count(session)

            # 统计激活的虚拟客户端
            count = await Client.count(
                session,
                (Client.user_id == user_id) & (Client.type != ClientTypeEnum.physical) & (Client.is_active == True)
            )

            # 使用 TimeFilterRequest 进行时间筛选
            count = await User.count(session, time_filter=time_filter_request)

            # 使用独立时间参数
            count = await User.count(
                session,
                created_after_datetime=datetime(2025, 1, 1),
                created_before_datetime=datetime(2025, 2, 1),
            )
        """
        # time_filter 的时间筛选优先级更高
        if isinstance(time_filter, TimeFilterRequest):
            if time_filter.created_after_datetime is not None:
                created_after_datetime = time_filter.created_after_datetime
            if time_filter.created_before_datetime is not None:
                created_before_datetime = time_filter.created_before_datetime
            if time_filter.updated_after_datetime is not None:
                updated_after_datetime = time_filter.updated_after_datetime
            if time_filter.updated_before_datetime is not None:
                updated_before_datetime = time_filter.updated_before_datetime

        statement = select(func.count()).select_from(cls)

        # 应用查询条件
        if condition is not None:
            statement = statement.where(condition)

        # 应用时间筛选
        for time_condition in cls._build_time_filters(
            created_before_datetime, created_after_datetime,
            updated_before_datetime, updated_after_datetime
        ):
            statement = statement.where(time_condition)

        result = await session.scalar(statement)
        return result or 0

    @classmethod
    async def get_with_count(
            cls: type[T],
            session: AsyncSession,
            condition: BinaryExpression | ClauseElement | None = None,
            *,
            join: type[T] | tuple[type[T], _OnClauseArgument] | None = None,
            options: list | None = None,
            load: RelationshipInfo | list[RelationshipInfo] | None = None,
            order_by: list[ClauseElement] | None = None,
            filter: BinaryExpression | ClauseElement | None = None,
            table_view: TableViewRequest | None = None,
            jti_subclasses: list[type[PolymorphicBaseMixin]] | Literal['all'] | None = None,
    ) -> 'ListResponse[T]':
        """
        获取分页列表及总数，直接返回 ListResponse

        同时返回符合条件的记录列表和总数，用于分页场景。
        与 get() 方法类似，但固定 fetch_mode="all" 并返回 ListResponse。

        注意：如果子类的 get() 方法支持额外参数（如 filter_params），
        子类应该覆盖此方法以确保 count 和 items 使用相同的过滤条件。

        Args:
            session: 数据库会话
            condition: 查询条件
            join: JOIN 的模型类或元组
            options: SQLAlchemy 查询选项
            load: selectinload 预加载关系
            order_by: 排序子句
            filter: 附加过滤条件
            table_view: 分页排序参数（推荐使用）
            jti_subclasses: 多态子类加载选项

        Returns:
            ListResponse[T]: 包含 count 和 items 的分页响应

        Examples:
            ```python
            @router.get("", response_model=ListResponse[CharacterInfoResponse])
            async def list_characters(
                session: SessionDep,
                table_view: TableViewRequestDep
            ) -> ListResponse[Character]:
                return await Character.get_with_count(session, table_view=table_view)
            ```
        """
        # 提取时间筛选参数（用于 count）
        time_filter: TimeFilterRequest | None = None
        if table_view is not None:
            time_filter = TimeFilterRequest(
                created_after_datetime=table_view.created_after_datetime,
                created_before_datetime=table_view.created_before_datetime,
                updated_after_datetime=table_view.updated_after_datetime,
                updated_before_datetime=table_view.updated_before_datetime,
            )

        # 获取总数（不带分页限制）
        total_count = await cls.count(session, condition, time_filter=time_filter)

        # 获取分页数据
        items = await cls.get(
            session,
            condition,
            fetch_mode="all",
            join=join,
            options=options,
            load=load,
            order_by=order_by,
            filter=filter,
            table_view=table_view,
            jti_subclasses=jti_subclasses,
        )

        return ListResponse(count=total_count, items=items)

    @classmethod
    async def get_exist_one(cls: type[T], session: AsyncSession, id: int, load: RelationshipInfo | list[RelationshipInfo] | None = None) -> T:
        """
        根据主键 ID 获取一个存在的记录, 如果不存在则抛出 404 异常.

        这个方法是对 `get` 方法的封装，专门用于处理那种"记录必须存在"的业务场景。
        如果记录未找到，它会直接引发 FastAPI 的 `HTTPException`, 而不是返回 `None`.

        Args:
            session (AsyncSession): 用于数据库操作的异步会话对象.
            id (int): 要查找的记录的主键 ID.
            load (Relationship | None): 可选的，用于预加载的关联属性.

        Returns:
            T: 找到的模型实例.

        Raises:
            HTTPException: 如果 ID 对应的记录不存在，则抛出状态码为 404 的异常.
        """
        instance = await cls.get(session, cls.id == id, load=load)
        if not instance:
            raise HTTPException(status_code=404, detail="Not found")
        return instance

class UUIDTableBaseMixin(TableBaseMixin):
    """
    一个使用 UUID 作为主键的异步 CRUD 操作基础模型类 Mixin.

    此类继承自 `TableBaseMixin`, 将主键 `id` 的类型覆盖为 `uuid.UUID`，
    并为新记录自动生成 UUID. 它继承了 `TableBaseMixin` 的所有 CRUD 方法.

    Attributes:
        id (uuid.UUID): UUID 类型的主键, 在创建时自动生成.
    """
    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    """覆盖 `TableBaseMixin` 的 id 字段，使用 UUID 作为主键."""

    @override
    @classmethod
    async def get_exist_one(cls: type[T], session: AsyncSession, id: uuid.UUID, load: Relationship | None = None) -> T:
        """
        根据 UUID 主键获取一个存在的记录, 如果不存在则抛出 404 异常.

        此方法覆盖了父类的同名方法，以确保 `id` 参数的类型注解为 `uuid.UUID`,
        从而提供更好的类型安全和代码提示.

        Args:
            session (AsyncSession): 用于数据库操作的异步会话对象.
            id (uuid.UUID): 要查找的记录的 UUID 主键.
            load (Relationship | None): 可选的，用于预加载的关联属性.

        Returns:
            T: 找到的模型实例.

        Raises:
            HTTPException: 如果 UUID 对应的记录不存在，则抛出状态码为 404 的异常.
        """
        # 类型检查器可能会警告这里的 `id` 类型不匹配超类方法，
        # 但在运行时这是正确的，因为超类方法内部的比较 (cls.id == id)
        # 会正确处理 UUID 类型。`type: ignore` 用于抑制此警告。
        return await super().get_exist_one(session, id, load) # type: ignore
