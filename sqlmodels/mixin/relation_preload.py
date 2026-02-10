"""
关系预加载 Mixin

提供方法级别的关系声明和按需增量加载，避免 MissingGreenlet 错误，同时保证 SQL 查询数理论最优。

设计原则：
- 按需加载：只加载被调用方法需要的关系
- 增量加载：已加载的关系不重复加载
- 查询最优：相同关系只查询一次，不同关系增量查询
- 零侵入：调用方无需任何改动
- Commit 安全：基于 SQLAlchemy inspect 检测真实加载状态，自动处理 expire

使用方式：
    from sqlmodels.mixin import RelationPreloadMixin, requires_relations

    class KlingO1VideoFunction(RelationPreloadMixin, Function, table=True):
        kling_video_generator: KlingO1Generator = Relationship(...)

        @requires_relations('kling_video_generator', KlingO1Generator.kling_o1)
        async def cost(self, params, context, session) -> ToolCost:
            # 自动加载，可以安全访问
            price = self.kling_video_generator.kling_o1.pro_price_per_second
            ...

    # 调用方 - 无需任何改动
    await tool.cost(params, context, session)  # 自动加载 cost 需要的关系
    await tool._call(...)  # 关系相同则跳过，否则增量加载

支持 AsyncGenerator：
    @requires_relations('twitter_api')
    async def _call(self, ...) -> AsyncGenerator[ToolResponse, None]:
        yield ToolResponse(...)  # 装饰器正确处理 async generator
"""
import inspect as python_inspect
from functools import wraps
from typing import Callable, TypeVar, ParamSpec, Any

from loguru import logger as l
from sqlalchemy import inspect as sa_inspect
from sqlmodel.ext.asyncio.session import AsyncSession
from sqlmodel.main import RelationshipInfo

P = ParamSpec('P')
R = TypeVar('R')


def _extract_session(
    func: Callable,
    args: tuple[Any, ...],
    kwargs: dict[str, Any],
) -> AsyncSession | None:
    """
    从方法参数中提取 AsyncSession

    按以下顺序查找：
    1. kwargs 中名为 'session' 的参数
    2. 根据函数签名定位 'session' 参数的位置，从 args 提取
    3. kwargs 中类型为 AsyncSession 的参数
    """
    # 1. 优先从 kwargs 查找
    if 'session' in kwargs:
        return kwargs['session']

    # 2. 从函数签名定位位置参数
    try:
        sig = python_inspect.signature(func)
        param_names = list(sig.parameters.keys())

        if 'session' in param_names:
            # 计算位置（减去 self）
            idx = param_names.index('session') - 1
            if 0 <= idx < len(args):
                return args[idx]
    except (ValueError, TypeError):
        pass

    # 3. 遍历 kwargs 找 AsyncSession 类型
    for value in kwargs.values():
        if isinstance(value, AsyncSession):
            return value

    return None


def _is_obj_relation_loaded(obj: Any, rel_name: str) -> bool:
    """
    检查对象的关系是否已加载（独立函数版本）

    Args:
        obj: 要检查的对象
        rel_name: 关系属性名

    Returns:
        True 如果关系已加载，False 如果未加载或已过期
    """
    try:
        state = sa_inspect(obj)
        return rel_name not in state.unloaded
    except Exception:
        return False


def _find_relation_to_class(from_class: type, to_class: type) -> str | None:
    """
    在类中查找指向目标类的关系属性名

    Args:
        from_class: 源类
        to_class: 目标类

    Returns:
        关系属性名，如果找不到则返回 None

    Example:
        _find_relation_to_class(KlingO1VideoFunction, KlingO1Generator)
        # 返回 'kling_video_generator'
    """
    for attr_name in dir(from_class):
        try:
            attr = getattr(from_class, attr_name, None)
            if attr is None:
                continue
            # 检查是否是 SQLAlchemy InstrumentedAttribute（关系属性）
            # parent.class_ 是关系所在的类，property.mapper.class_ 是关系指向的目标类
            if hasattr(attr, 'property') and hasattr(attr.property, 'mapper'):
                target_class = attr.property.mapper.class_
                if target_class == to_class:
                    return attr_name
        except AttributeError:
            continue
    return None


def requires_relations(*relations: str | RelationshipInfo) -> Callable[[Callable[P, R]], Callable[P, R]]:
    """
    装饰器：声明方法需要的关系，自动按需增量加载

    参数格式：
    - 字符串：本类属性名，如 'kling_video_generator'
    - RelationshipInfo：外部类属性，如 KlingO1Generator.kling_o1

    行为：
    - 方法调用时自动检查关系是否已加载
    - 未加载的关系会被增量加载（单次查询）
    - 已加载的关系直接跳过

    支持：
    - 普通 async 方法：`async def cost(...) -> ToolCost`
    - AsyncGenerator 方法：`async def _call(...) -> AsyncGenerator[ToolResponse, None]`

    Example:
        @requires_relations('kling_video_generator', KlingO1Generator.kling_o1)
        async def cost(self, params, context, session) -> ToolCost:
            # self.kling_video_generator.kling_o1 已自动加载
            ...

        @requires_relations('twitter_api')
        async def _call(self, ...) -> AsyncGenerator[ToolResponse, None]:
            yield ToolResponse(...)  # AsyncGenerator 正确处理

    验证：
    - 字符串格式的关系名在类创建时（__init_subclass__）验证
    - 拼写错误会在导入时抛出 AttributeError
    """
    def decorator(func: Callable[P, R]) -> Callable[P, R]:
        # 检测是否是 async generator 函数
        is_async_gen = python_inspect.isasyncgenfunction(func)

        if is_async_gen:
            # AsyncGenerator 需要特殊处理：wrapper 也必须是 async generator
            @wraps(func)
            async def wrapper(self, *args: P.args, **kwargs: P.kwargs) -> R:
                session = _extract_session(func, args, kwargs)
                if session is not None:
                    await self._ensure_relations_loaded(session, relations)
                # 委托给原始 async generator，逐个 yield 值
                async for item in func(self, *args, **kwargs):
                    yield item  # type: ignore
        else:
            # 普通 async 函数：await 并返回结果
            @wraps(func)
            async def wrapper(self, *args: P.args, **kwargs: P.kwargs) -> R:
                session = _extract_session(func, args, kwargs)
                if session is not None:
                    await self._ensure_relations_loaded(session, relations)
                return await func(self, *args, **kwargs)

        # 保存关系声明供验证和内省使用
        wrapper._required_relations = relations  # type: ignore
        return wrapper

    return decorator


class RelationPreloadMixin:
    """
    关系预加载 Mixin

    提供按需增量加载能力，确保 SQL 查询数理论最优。

    特性：
    - 按需加载：只加载被调用方法需要的关系
    - 增量加载：已加载的关系不重复加载
    - 原地更新：直接修改 self，无需替换实例
    - 导入时验证：字符串关系名在类创建时验证
    - Commit 安全：基于 SQLAlchemy inspect 检测真实状态，自动处理 expire
    """

    def __init_subclass__(cls, **kwargs) -> None:
        """类创建时验证所有 @requires_relations 声明"""
        super().__init_subclass__(**kwargs)

        # 收集类及其父类的所有注解（包含普通字段）
        all_annotations: set[str] = set()
        for klass in cls.__mro__:
            if hasattr(klass, '__annotations__'):
                all_annotations.update(klass.__annotations__.keys())

        # 收集 SQLModel 的 Relationship 字段（存储在 __sqlmodel_relationships__）
        sqlmodel_relationships: set[str] = set()
        for klass in cls.__mro__:
            if hasattr(klass, '__sqlmodel_relationships__'):
                sqlmodel_relationships.update(klass.__sqlmodel_relationships__.keys())

        # 合并所有可用的属性名
        all_available_names = all_annotations | sqlmodel_relationships

        for method_name in dir(cls):
            if method_name.startswith('__'):
                continue

            try:
                method = getattr(cls, method_name, None)
            except AttributeError:
                continue

            if method is None or not hasattr(method, '_required_relations'):
                continue

            # 验证字符串格式的关系名
            for spec in method._required_relations:
                if isinstance(spec, str):
                    # 检查注解、Relationship 或已有属性
                    if spec not in all_available_names and not hasattr(cls, spec):
                        raise AttributeError(
                            f"{cls.__name__}.{method_name} 声明了关系 '{spec}'，"
                            f"但 {cls.__name__} 没有此属性"
                        )

    def _is_relation_loaded(self, rel_name: str) -> bool:
        """
        检查关系是否真正已加载（基于 SQLAlchemy inspect）

        使用 SQLAlchemy 的 inspect 检测真实加载状态，
        自动处理 commit 导致的 expire 问题。

        Args:
            rel_name: 关系属性名

        Returns:
            True 如果关系已加载，False 如果未加载或已过期
        """
        try:
            state = sa_inspect(self)
            # unloaded 包含未加载的关系属性名
            return rel_name not in state.unloaded
        except Exception:
            # 对象可能未被 SQLAlchemy 管理
            return False

    async def _ensure_relations_loaded(
        self,
        session: AsyncSession,
        relations: tuple[str | RelationshipInfo, ...],
    ) -> None:
        """
        确保指定关系已加载，只加载未加载的部分

        基于 SQLAlchemy inspect 检测真实状态，自动处理：
        - 首次访问的关系
        - commit 后 expire 的关系
        - 嵌套关系（如 KlingO1Generator.kling_o1）

        Args:
            session: 数据库会话
            relations: 需要的关系规格
        """
        # 找出真正未加载的关系（基于 SQLAlchemy inspect）
        to_load: list[str | RelationshipInfo] = []
        # 区分直接关系和嵌套关系的 key
        direct_keys: set[str] = set()  # 本类的直接关系属性名
        nested_parent_keys: set[str] = set()  # 嵌套关系所需的父关系属性名

        for rel in relations:
            if isinstance(rel, str):
                # 直接关系：检查本类的关系是否已加载
                if not self._is_relation_loaded(rel):
                    to_load.append(rel)
                    direct_keys.add(rel)
            else:
                # 嵌套关系（InstrumentedAttribute）：如 KlingO1Generator.kling_o1
                # 1. 查找指向父类的关系属性
                parent_class = rel.parent.class_
                parent_attr = _find_relation_to_class(self.__class__, parent_class)

                if parent_attr is None:
                    # 找不到路径，可能是配置错误，但仍尝试加载
                    l.warning(
                        f"无法找到从 {self.__class__.__name__} 到 {parent_class.__name__} 的关系路径，"
                        f"无法检查 {rel.key} 是否已加载"
                    )
                    to_load.append(rel)
                    continue

                # 2. 检查父对象是否已加载
                if not self._is_relation_loaded(parent_attr):
                    # 父对象未加载，需要同时加载父对象和嵌套关系
                    if parent_attr not in direct_keys and parent_attr not in nested_parent_keys:
                        to_load.append(parent_attr)
                        nested_parent_keys.add(parent_attr)
                    to_load.append(rel)
                else:
                    # 3. 父对象已加载，检查嵌套关系是否已加载
                    parent_obj = getattr(self, parent_attr)
                    if not _is_obj_relation_loaded(parent_obj, rel.key):
                        # 嵌套关系未加载：需要同时传递父关系和嵌套关系
                        # 因为 _build_load_chains 需要完整的链来构建 selectinload
                        if parent_attr not in direct_keys and parent_attr not in nested_parent_keys:
                            to_load.append(parent_attr)
                            nested_parent_keys.add(parent_attr)
                        to_load.append(rel)

        if not to_load:
            return  # 全部已加载，跳过

        # 构建 load 参数
        load_options = self._specs_to_load_options(to_load)
        if not load_options:
            return

        # 安全地获取主键值（避免触发懒加载）
        state = sa_inspect(self)
        pk_tuple = state.key[1] if state.key else None
        if pk_tuple is None:
            l.warning(f"无法获取 {self.__class__.__name__} 的主键值")
            return
        # 主键是元组，取第一个值（假设单列主键）
        pk_value = pk_tuple[0]

        # 单次查询加载缺失的关系
        fresh = await self.__class__.get(
            session,
            self.__class__.id == pk_value,
            load=load_options,
        )

        if fresh is None:
            l.warning(f"无法加载关系：{self.__class__.__name__} id={self.id} 不存在")
            return

        # 原地复制到 self（只复制直接关系，嵌套关系通过父关系自动可访问）
        all_direct_keys = direct_keys | nested_parent_keys
        for key in all_direct_keys:
            value = getattr(fresh, key, None)
            object.__setattr__(self, key, value)

    def _specs_to_load_options(
        self,
        specs: list[str | RelationshipInfo],
    ) -> list[RelationshipInfo]:
        """
        将关系规格转换为 load 参数

        - 字符串 → cls.{name}
        - RelationshipInfo → 直接使用
        """
        result: list[RelationshipInfo] = []

        for spec in specs:
            if isinstance(spec, str):
                rel = getattr(self.__class__, spec, None)
                if rel is not None:
                    result.append(rel)
                else:
                    l.warning(f"关系 '{spec}' 在类 {self.__class__.__name__} 中不存在")
            else:
                result.append(spec)

        return result

    # ==================== 可选的手动预加载 API ====================

    @classmethod
    def get_relations_for_method(cls, method_name: str) -> list[RelationshipInfo]:
        """
        获取指定方法声明的关系（用于外部预加载场景）

        Args:
            method_name: 方法名

        Returns:
            RelationshipInfo 列表
        """
        method = getattr(cls, method_name, None)
        if method is None or not hasattr(method, '_required_relations'):
            return []

        result: list[RelationshipInfo] = []
        for spec in method._required_relations:
            if isinstance(spec, str):
                rel = getattr(cls, spec, None)
                if rel:
                    result.append(rel)
            else:
                result.append(spec)

        return result

    @classmethod
    def get_relations_for_methods(cls, *method_names: str) -> list[RelationshipInfo]:
        """
        获取多个方法的关系并去重（用于批量预加载场景）

        Args:
            method_names: 方法名列表

        Returns:
            去重后的 RelationshipInfo 列表
        """
        seen: set[str] = set()
        result: list[RelationshipInfo] = []

        for method_name in method_names:
            for rel in cls.get_relations_for_method(method_name):
                key = rel.key
                if key not in seen:
                    seen.add(key)
                    result.append(rel)

        return result

    async def preload_for(self, session: AsyncSession, *method_names: str) -> 'RelationPreloadMixin':
        """
        手动预加载指定方法的关系（可选优化 API）

        当需要确保在调用方法前完成所有加载时使用。
        通常情况下不需要调用此方法，装饰器会自动处理。

        Args:
            session: 数据库会话
            method_names: 方法名列表

        Returns:
            self（支持链式调用）

        Example:
            # 可选：显式预加载（通常不需要）
            tool = await tool.preload_for(session, 'cost', '_call')
        """
        all_relations: list[str | RelationshipInfo] = []

        for method_name in method_names:
            method = getattr(self.__class__, method_name, None)
            if method and hasattr(method, '_required_relations'):
                all_relations.extend(method._required_relations)

        if all_relations:
            await self._ensure_relations_loaded(session, tuple(all_relations))

        return self
