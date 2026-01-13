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
"""
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
from sqlalchemy import DateTime, BinaryExpression, ClauseElement, desc, asc, func, distinct
from sqlalchemy.orm import selectinload, Relationship, with_polymorphic
from sqlmodel import Field, select
from sqlmodel.ext.asyncio.session import AsyncSession
from sqlalchemy.sql._typing import _OnClauseArgument
from sqlalchemy.ext.asyncio import AsyncAttrs
from sqlmodel.main import RelationshipInfo

from .polymorphic import PolymorphicBaseMixin
from models.base.sqlmodel_base import SQLModelBase

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
    _is_table_mixin: ClassVar[bool] = True
    """标记此类为表混入类的内部属性"""

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
    async def add(cls: type[T], session: AsyncSession, instances: T | list[T], refresh: bool = True, commit: bool = True) -> T | list[T]:
        """
        向数据库中添加一个新的或多个新的记录.

        这个类方法可以接受单个模型实例或一个实例列表，并将它们
        一次性提交到数据库中。执行后，可以选择性地刷新这些实例以获取
        数据库生成的值（例如，自动递增的 ID）.

        Args:
            session (AsyncSession): 用于数据库操作的异步会话对象.
            instances (T | list[T]): 要添加的单个模型实例或模型实例列表.
            refresh (bool): 如果为 True, 将在提交后刷新实例以同步数据库状态. 默认为 True.
            commit (bool): 是否提交事务。设为 False 可在批量操作时减少提交次数，
                          之后需要手动调用 `session.commit()`。默认为 True.

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

            # 批量操作，减少提交次数
            await Item.add(session, [item1, item2], commit=False)
            await Item.add(session, [item3, item4], commit=False)
            await session.commit()
        """
        is_list = False
        if isinstance(instances, list):
            is_list = True
            session.add_all(instances)
        else:
            session.add(instances)

        if commit:
            await session.commit()
        else:
            await session.flush()

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
            commit: bool = True
    ) -> T:
        """
        保存（插入或更新）当前模型实例到数据库.

        这是一个实例方法，它将当前对象添加到会话中并提交更改。
        可以用于创建新记录或更新现有记录。还可以选择在保存后
        预加载（eager load）一个或多个关联关系.

        **重要**：调用此方法后，session中的所有对象都会过期（expired）。
        如果需要继续使用该对象，必须使用返回值：

        ```python
        # ✅ 正确：需要返回值时
        client = await client.save(session)
        return client

        # ✅ 正确：不需要返回值时，指定 refresh=False 节省性能
        await client.save(session, refresh=False)

        # ✅ 正确：批量操作，减少提交次数
        await item1.save(session, commit=False)
        await item2.save(session, commit=False)
        await session.commit()

        # ✅ 正确：批量操作并预加载多个关联关系
        user = await user.save(session, load=[User.group, User.tags])

        # ❌ 错误：需要返回值但未使用
        await client.save(session)
        return client  # client 对象已过期
        ```

        Args:
            session (AsyncSession): 用于数据库操作的异步会话对象.
            load (Relationship | list[Relationship] | None): 可选的，指定在保存和刷新后要预加载的关联属性.
                                                         可以是单个关系或关系列表.
                                                         例如 `User.posts` 或 `[User.group, User.tags]`.
            refresh (bool): 是否在保存后刷新对象。如果不需要使用返回值，
                           设为 False 可节省一次数据库查询。默认为 True.
            commit (bool): 是否提交事务。设为 False 可在批量操作时减少提交次数，
                          之后需要手动调用 `session.commit()`。默认为 True.

        Returns:
            T: 如果 refresh=True，返回已刷新的模型实例；否则返回未刷新的 self.
        """
        session.add(self)
        if commit:
            await session.commit()
        else:
            await session.flush()

        if not refresh:
            return self

        if load is not None:
            cls = type(self)
            await session.refresh(self)
            # 如果指定了 load, 重新获取实例并加载关联关系
            return await cls.get(session, cls.id == self.id, load=load)
        else:
            await session.refresh(self)
            return self

    async def update(
            self: T,
            session: AsyncSession,
            other: M,
            extra_data: dict[str, Any] | None = None,
            exclude_unset: bool = True,
            exclude: set[str] | None = None,
            load: RelationshipInfo | list[RelationshipInfo] | None = None,
            refresh: bool = True,
            commit: bool = True
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

        # ✅ 正确：不需要返回值时，指定 refresh=False 节省性能
        await client.update(session, update_data, refresh=False)

        # ✅ 正确：批量操作，减少提交次数
        await user1.update(session, data1, commit=False)
        await user2.update(session, data2, commit=False)
        await session.commit()

        # ✅ 正确：批量操作并预加载多个关联关系
        user = await user.update(session, data, load=[User.group, User.tags])

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
            load (Relationship | list[Relationship] | None): 可选的，指定在更新和刷新后要预加载的关联属性.
                                                        可以是单个关系或关系列表.
                                                        例如 `User.permission` 或 `[User.group, User.tags]`.
            refresh (bool): 是否在更新后刷新对象。如果不需要使用返回值，
                           设为 False 可节省一次数据库查询。默认为 True.
            commit (bool): 是否提交事务。设为 False 可在批量操作时减少提交次数，
                          之后需要手动调用 `session.commit()`。默认为 True.

        Returns:
            T: 如果 refresh=True，返回已刷新的模型实例；否则返回未刷新的 self.
        """
        self.sqlmodel_update(
            other.model_dump(exclude_unset=exclude_unset, exclude=exclude),
            update=extra_data
        )

        session.add(self)
        if commit:
            await session.commit()
        else:
            await session.flush()

        if not refresh:
            return self

        if load is not None:
            cls = type(self)
            await session.refresh(self)
            return await cls.get(session, cls.id == self.id, load=load)
        else:
            await session.refresh(self)
            return self

    @classmethod
    async def delete(
        cls: type[T],
        session: AsyncSession,
        instances: T | list[T] | None = None,
        *,
        condition: BinaryExpression | ClauseElement | None = None,
        commit: bool = True
    ) -> int:
        """
        从数据库中删除记录.

        支持两种删除方式：
        1. 实例删除：传入 instances 参数，先加载再删除
        2. 条件删除：传入 condition 参数，直接 SQL 删除（更高效）

        Args:
            session (AsyncSession): 用于数据库操作的异步会话对象.
            instances (T | list[T] | None): 要删除的单个模型实例或模型实例列表（可选）.
            condition (BinaryExpression | ClauseElement | None): 删除条件（可选，与 instances 二选一）.
            commit (bool): 是否提交事务。设为 False 可在批量操作时减少提交次数，
                          之后需要手动调用 `session.commit()`。默认为 True.

        Returns:
            int: 删除的记录数量

        Usage:
            # 实例删除
            item_to_delete = await Item.get(session, Item.id == 1)
            if item_to_delete:
                deleted_count = await Item.delete(session, item_to_delete)

            # 条件删除（更高效，无需加载实例）
            deleted_count = await Item.delete(
                session,
                condition=(Item.status == "inactive") & (Item.created_at < cutoff_date)
            )

            # 批量删除后手动提交
            await Item.delete(session, item1, commit=False)
            await Item.delete(session, item2, commit=False)
            await session.commit()
        """
        # 条件删除模式
        if condition is not None:
            from sqlmodel import delete as sql_delete

            if instances is not None:
                raise ValueError("不能同时指定 instances 和 condition")

            # 执行条件删除
            stmt = sql_delete(cls).where(condition)
            result = await session.exec(stmt)
            deleted_count = result.rowcount

            if commit:
                await session.commit()

            return deleted_count

        # 实例删除模式（原有逻辑）
        if instances is None:
            raise ValueError("必须指定 instances 或 condition")

        deleted_count = 0
        if isinstance(instances, list):
            for instance in instances:
                await session.delete(instance)
                deleted_count += 1
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
            load_polymorphic: list[type[PolymorphicBaseMixin]] | Literal['all'] | None = None,
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
                                                         可以是单个关系或关系列表.
                                                         例如 `User.profile` 或 `[User.group, User.tags]`.
            order_by (list[ClauseElement] | None): 用于排序的排序列或表达式的列表.
                                                   例如 `[User.name.asc(), User.created_at.desc()]`.
            filter (BinaryExpression | ClauseElement | None): 附加的过滤条件.

            with_for_update (bool): 如果为 True, 在查询中使用 `FOR UPDATE` 锁定选定的行. 默认为 False.

            table_view (TableViewRequest | None): TableViewRequest对象，如果提供则自动处理分页、排序和时间筛选。
                                                  会覆盖offset、limit、order_by及时间筛选参数。
                                                  这是推荐的分页排序方式，统一了所有LIST端点的参数格式。

            load_polymorphic: 多态子类加载选项，需要与 load 参数配合使用。
                - list[type[PolymorphicBaseMixin]]: 指定要加载的子类列表
                - 'all': 两阶段查询，只加载实际关联的子类（对于 > 10 个子类的场景有明显性能收益）
                - None（默认）: 不使用多态加载

            created_before_datetime (datetime | None): 筛选 created_at < datetime 的记录
            created_after_datetime (datetime | None): 筛选 created_at >= datetime 的记录
            updated_before_datetime (datetime | None): 筛选 updated_at < datetime 的记录
            updated_after_datetime (datetime | None): 筛选 updated_at >= datetime 的记录

        Returns:
            T | list[T] | None: 根据 `fetch_mode` 的设置，返回单个实例、实例列表或 `None`.

        Raises:
            ValueError: 如果提供了无效的 `fetch_mode` 值，或 load_polymorphic 未与 load 配合使用.

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
                load_polymorphic='all'  # 只加载实际关联的子类
            )
        """
        # 参数验证：load_polymorphic 需要与 load 配合使用
        if load_polymorphic is not None and load is None:
            raise ValueError(
                "load_polymorphic 参数需要与 load 参数配合使用，"
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
        if issubclass(cls, PolymorphicBaseMixin):
            # '*' 表示加载所有子类
            polymorphic_cls = with_polymorphic(cls, '*')
            statement = select(polymorphic_cls)
        else:
            statement = select(cls)

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

            # 处理多态加载
            if load_polymorphic is not None:
                # 多态加载只支持单个关系
                if len(load_list) > 1:
                    raise ValueError("load_polymorphic 仅支持单个关系")
                target_class = load_list[0].property.mapper.class_

                # 检查目标类是否继承自 PolymorphicBaseMixin
                if not issubclass(target_class, PolymorphicBaseMixin):
                    raise ValueError(
                        f"目标类 {target_class.__name__} 不是多态类，"
                        f"请确保其继承自 PolymorphicBaseMixin"
                    )

                if load_polymorphic == 'all':
                    # 两阶段查询：获取实际关联的多态类型
                    subclasses_to_load = await cls._resolve_polymorphic_subclasses(
                        session, condition, load_list[0], target_class
                    )
                else:
                    subclasses_to_load = load_polymorphic

                if subclasses_to_load:
                    # 关键：selectin_polymorphic 必须作为 selectinload 的链式子选项
                    # 参考: https://docs.sqlalchemy.org/en/20/orm/queryguide/relationships.html#polymorphic-eager-loading
                    statement = statement.options(
                        selectinload(load_list[0]).selectin_polymorphic(subclasses_to_load)
                    )
                else:
                    statement = statement.options(selectinload(load_list[0]))
            else:
                # 为每个关系添加 selectinload
                for rel in load_list:
                    statement = statement.options(selectinload(rel))

        if order_by is not None:
            statement = statement.order_by(*order_by)

        if offset:
            statement = statement.offset(offset)

        if limit:
            statement = statement.limit(limit)

        if filter:
            statement = statement.filter(filter)

        if with_for_update:
            statement = statement.with_for_update()

        result = await session.exec(statement)

        if fetch_mode == "one":
            return result.one()
        elif fetch_mode == "first":
            return result.first()
        elif fetch_mode == "all":
            return list(result.all())
        else:
            raise ValueError(f"无效的 fetch_mode: {fetch_mode}")

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
            # 一对多关系：通过外键查询
            foreign_key_col = relationship_property.local_remote_pairs[0][1]
            type_query = (
                select(distinct(poly_name_col))
                .where(foreign_key_col.in_(
                    select(cls.id).where(condition) if condition is not None else select(cls.id)
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
            load_polymorphic: list[type[PolymorphicBaseMixin]] | Literal['all'] | None = None,
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
            load_polymorphic: 多态子类加载选项

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
            load_polymorphic=load_polymorphic,
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
            load (Relationship | list[Relationship] | None): 可选的，用于预加载的关联属性.
                                                           可以是单个关系或关系列表.

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
    async def get_exist_one(cls: type[T], session: AsyncSession, id: uuid.UUID, load: Relationship | list[Relationship] | None = None) -> T:
        """
        根据 UUID 主键获取一个存在的记录, 如果不存在则抛出 404 异常.

        此方法覆盖了父类的同名方法，以确保 `id` 参数的类型注解为 `uuid.UUID`,
        从而提供更好的类型安全和代码提示.

        Args:
            session (AsyncSession): 用于数据库操作的异步会话对象.
            id (uuid.UUID): 要查找的记录的 UUID 主键.
            load (Relationship | list[Relationship] | None): 可选的，用于预加载的关联属性.
                                                           可以是单个关系或关系列表.

        Returns:
            T: 找到的模型实例.

        Raises:
            HTTPException: 如果 UUID 对应的记录不存在，则抛出状态码为 404 的异常.
        """
        # 类型检查器可能会警告这里的 `id` 类型不匹配超类方法，
        # 但在运行时这是正确的，因为超类方法内部的比较 (cls.id == id)
        # 会正确处理 UUID 类型。`type: ignore` 用于抑制此警告。
        return await super().get_exist_one(session, id, load) # type: ignore
