# sqlmodel-ext API 完整参考

## 目录

- [SQLModelBase 与元类](#sqlmodelbase-与元类)
- [CRUD API](#crud-api)
- [分页模型](#分页模型)
- [多态继承](#多态继承)
- [乐观锁](#乐观锁)
- [关系预加载](#关系预加载)
- [Redis 缓存](#redis-缓存)
- [响应 DTO Mixin](#响应-dto-mixin)
- [字段类型](#字段类型)
- [PostgreSQL 类型](#postgresql-类型)
- [静态分析器](#静态分析器)
- [工具函数与异常](#工具函数与异常)

---

## SQLModelBase 与元类

### `SQLModelBase`

所有模型的基类。使用自定义元类 `__DeclarativeMeta`，提供：

1. **自动 `table=True`**：检测到继承链中有 `TableBaseMixin` 时自动设置
2. **`__mapper_args__` 合并**：子类继承并合并父类的 mapper 配置
3. **`sa_type` 提取**：从 `Annotated` 元数据中提取 SQLAlchemy 列类型
4. **属性 docstring 继承**：子类覆盖字段时自动继承父类的 description
5. **Python 3.14 (PEP 649) 兼容**：自动应用猴子补丁
6. **`all_fields_optional`**：子类声明时传入，自动将所有继承字段变为可选

```python
class ArticleBase(SQLModelBase):
    title: Str64
    """文章标题"""  # 自动出现在 OpenAPI schema
    body: Text10K

class ArticleUpdate(ArticleBase, all_fields_optional=True):
    pass  # title: Str64 | None = None, body: Text10K | None = None
```

**ConfigDict:** `extra='forbid'`, `validate_by_name=True`, `use_attribute_docstrings=True`

### `ExtraIgnoreModelBase`

同 `SQLModelBase`，但 `extra='ignore'`，遇到未知字段时记录 WARNING 而非拒绝。

---

## CRUD API

### `TableBaseMixin.add()`

批量插入一个或多个记录。

```python
@classmethod
async def add(
    cls,
    session: AsyncSession,
    instances: T | list[T],
    refresh: bool = True,
    commit: bool = True,
) -> T | list[T]
```

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `session` | `AsyncSession` | 必填 | 异步数据库会话 |
| `instances` | `T \| list[T]` | 必填 | 单个或多个实例 |
| `refresh` | `bool` | `True` | commit 后是否 refresh 以同步数据库生成的值 |
| `commit` | `bool` | `True` | 是否提交事务；`False` 时仅 flush |

### `TableBaseMixin.save()`

插入或更新当前实例。**必须使用返回值。**

```python
async def save(
    self,
    session: AsyncSession,
    load: QueryableAttribute | list[QueryableAttribute] | None = None,
    refresh: bool = True,
    commit: bool = True,
    jti_subclasses: list[type] | Literal['all'] | None = None,
    optimistic_retry_count: int = 0,
) -> T
```

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `session` | `AsyncSession` | 必填 | 异步数据库会话 |
| `load` | `QueryableAttribute \| list` | `None` | 保存后预加载的关系 |
| `refresh` | `bool` | `True` | 保存后是否从数据库刷新 |
| `commit` | `bool` | `True` | 是否提交事务。批量操作设 `False` |
| `jti_subclasses` | `list[type] \| 'all'` | `None` | 多态子类加载（需配合 `load`） |
| `optimistic_retry_count` | `int` | `0` | 乐观锁冲突时的自动重试次数 |

**抛出：** `OptimisticLockError`（重试耗尽后）

**乐观锁重试流程：** 捕获 `StaleDataError` -> 保存当前数据 -> 重新从 DB 查询最新记录 -> 重新应用修改 -> 重试 commit

### `TableBaseMixin.update()`

从另一个模型实例局部更新当前实例。**必须使用返回值。**

```python
async def update(
    self,
    session: AsyncSession,
    other: SQLModelBase,
    extra_data: dict[str, Any] | None = None,
    exclude_unset: bool = True,
    exclude: set[str] | None = None,
    load: QueryableAttribute | list[QueryableAttribute] | None = None,
    refresh: bool = True,
    commit: bool = True,
    jti_subclasses: list[type] | Literal['all'] | None = None,
    optimistic_retry_count: int = 0,
) -> T
```

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `session` | `AsyncSession` | 必填 | 异步数据库会话 |
| `other` | `SQLModelBase` | 必填 | 数据来源模型，其已设置字段将合并 |
| `extra_data` | `dict` | `None` | 额外更新字段 |
| `exclude_unset` | `bool` | `True` | 跳过 `other` 中未显式设置的字段 |
| `exclude` | `set[str]` | `None` | 要排除的字段名称集合 |
| `load` | 同 save | `None` | 更新后预加载的关系 |
| `refresh` | `bool` | `True` | 更新后是否刷新 |
| `commit` | `bool` | `True` | 是否提交事务 |
| `jti_subclasses` | 同 save | `None` | 多态子类加载 |
| `optimistic_retry_count` | `int` | `0` | 乐观锁自动重试次数 |

### `TableBaseMixin.delete()`

按实例或条件删除。`instances` 和 `condition` 二选一。

```python
@classmethod
async def delete(
    cls,
    session: AsyncSession,
    instances: T | list[T] | None = None,
    *,
    condition: ColumnElement[bool] | None = None,
    commit: bool = True,
) -> int  # 返回删除数量
```

### `TableBaseMixin.get()`

核心查询方法，支持过滤、分页、排序、JOIN、关系加载、多态、时间过滤、行锁。

```python
@classmethod
async def get(
    cls,
    session: AsyncSession,
    condition: ColumnElement[bool] | None = None,
    *,
    offset: int | None = None,
    limit: int | None = None,
    fetch_mode: Literal["one", "first", "all"] = "first",
    join: type | tuple[type, _OnClauseArgument] | None = None,
    options: list[ExecutableOption] | None = None,
    load: QueryableAttribute | list[QueryableAttribute] | None = None,
    order_by: list[ColumnElement] | None = None,
    filter: ColumnElement[bool] | None = None,
    with_for_update: bool = False,
    table_view: TableViewRequest | None = None,
    jti_subclasses: list[type] | Literal['all'] | None = None,
    populate_existing: bool = False,
    created_before_datetime: datetime | None = None,
    created_after_datetime: datetime | None = None,
    updated_before_datetime: datetime | None = None,
    updated_after_datetime: datetime | None = None,
) -> T | list[T] | None
```

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `condition` | `ColumnElement[bool]` | `None` | WHERE 条件 |
| `offset` | `int` | `None` | 分页偏移量 |
| `limit` | `int` | `None` | 最大返回数 |
| `fetch_mode` | `"one"/"first"/"all"` | `"first"` | 获取模式 |
| `join` | `type \| tuple` | `None` | JOIN 目标（类或 (类, ON 条件)） |
| `options` | `list[ExecutableOption]` | `None` | SQLAlchemy 查询选项 |
| `load` | `QueryableAttribute \| list` | `None` | 关系预加载（selectinload） |
| `order_by` | `list[ColumnElement]` | `None` | 排序表达式 |
| `filter` | `ColumnElement[bool]` | `None` | 额外过滤条件 |
| `with_for_update` | `bool` | `False` | FOR UPDATE 行锁 |
| `table_view` | `TableViewRequest` | `None` | 分页+排序+时间过滤 |
| `jti_subclasses` | `list[type] \| 'all'` | `None` | 多态子类加载（需配合 `load`） |
| `populate_existing` | `bool` | `False` | 强制覆盖 identity map |
| `created/updated_*_datetime` | `datetime` | `None` | 时间过滤 |

**`load` 链式加载：** `load=[Parent.children, Child.toys]` 自动构建 `selectinload(children).selectinload(toys)`。

**FOR UPDATE 跟踪：** 被锁定的实例 `id()` 值记录在 `session.info[SESSION_FOR_UPDATE_KEY]` 中，供 `@requires_for_update` 验证。

**STI 子类自动过滤：** 对 STI 子类查询时，自动添加 `WHERE _polymorphic_name IN (...)` 过滤。

### `TableBaseMixin.count()`

数据库级 `COUNT(*)`。

```python
@classmethod
async def count(
    cls,
    session: AsyncSession,
    condition: ColumnElement[bool] | None = None,
    *,
    time_filter: TimeFilterRequest | None = None,
    created_before_datetime: datetime | None = None,
    created_after_datetime: datetime | None = None,
    updated_before_datetime: datetime | None = None,
    updated_after_datetime: datetime | None = None,
) -> int
```

### `TableBaseMixin.get_with_count()`

分页查询，返回 `ListResponse[T]`（总数 + 当前页数据）。

```python
@classmethod
async def get_with_count(
    cls,
    session: AsyncSession,
    condition: ColumnElement[bool] | None = None,
    *,
    join: type | tuple | None = None,
    options: list[ExecutableOption] | None = None,
    load: QueryableAttribute | list | None = None,
    order_by: list[ColumnElement] | None = None,
    filter: ColumnElement[bool] | None = None,
    table_view: TableViewRequest | None = None,
    jti_subclasses: list[type] | Literal['all'] | None = None,
) -> ListResponse[T]
```

### `TableBaseMixin.get_one()`

按主键 ID 获取恰好一条记录。等价于 `get(session, col(cls.id) == id, fetch_mode='one')`。

```python
@classmethod
async def get_one(
    cls,
    session: AsyncSession,
    id: int | UUID,
    *,
    load: QueryableAttribute | list | None = None,
    with_for_update: bool = False,
) -> T  # 不存在或多条时抛异常
```

### `TableBaseMixin.get_exist_one()`

按主键 ID 获取记录，不存在时抛 404。

```python
@classmethod
async def get_exist_one(
    cls,
    session: AsyncSession,
    id: int | UUID,
    load: QueryableAttribute | list | None = None,
) -> T
```

- 安装了 FastAPI 时抛出 `HTTPException(status_code=404)`
- 未安装 FastAPI 时抛出 `RecordNotFoundError`

### `sanitize_integrity_error()`

从 PostgreSQL IntegrityError 中提取用户友好的错误信息。

```python
@staticmethod
def sanitize_integrity_error(
    e: IntegrityError,
    default_message: str = "Data integrity constraint violation",
) -> str
```

仅提取 SQLSTATE 23514（check_violation，来自 `RAISE EXCEPTION ... USING ERRCODE = 'check_violation'`）的消息。其他约束错误返回 `default_message`。

### 辅助函数

```python
def rel(relationship: object) -> QueryableAttribute
```
将 SQLModel Relationship 字段窄化为 `QueryableAttribute`，用于 `load` 参数的类型安全。

```python
def cond(expr: ColumnElement[bool] | bool) -> ColumnElement[bool]
```
将 SQLModel 列比较窄化为 `ColumnElement[bool]`，使 `&` / `|` 运算通过类型检查。

```python
async def safe_reset(session: AsyncSession) -> None
```
`session.reset()` + 清理 FOR UPDATE 锁跟踪。用于长生命周期 session 的安全重置。

---

## 分页模型

### `ListResponse[T]`

泛型分页响应。继承 `BaseModel`（非 SQLModel，因 SQLModel Generic 有 schema 生成 bug）。

| 字段 | 类型 | 说明 |
|------|------|------|
| `count` | `int` | 匹配总数 |
| `items` | `list[T]` | 当前页记录 |

### `TimeFilterRequest`

时间过滤请求参数。验证 `after < before` 的一致性。

| 字段 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `created_after_datetime` | `datetime \| None` | `None` | `created_at >= 值` |
| `created_before_datetime` | `datetime \| None` | `None` | `created_at < 值` |
| `updated_after_datetime` | `datetime \| None` | `None` | `updated_at >= 值` |
| `updated_before_datetime` | `datetime \| None` | `None` | `updated_at < 值` |

### `PaginationRequest`

分页和排序请求参数。

| 字段 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `offset` | `int \| None` | `0` | 跳过前 N 条 |
| `limit` | `int \| None` | `50` | 每页最大数（上限 100） |
| `desc` | `bool \| None` | `True` | 是否降序 |
| `order` | `Literal["created_at", "updated_at"] \| None` | `"created_at"` | 排序字段 |

### `TableViewRequest`

组合 `TimeFilterRequest` + `PaginationRequest`。FastAPI 依赖注入用法：

```python
from typing import Annotated
from fastapi import Depends
from sqlmodel_ext import TableViewRequest

TableViewDep = Annotated[TableViewRequest, Depends()]
```

---

## 多态继承

### `PolymorphicBaseMixin`

自动配置多态设置的 Mixin。

- 添加 `_polymorphic_name: Mapped[str]` 鉴别列（带索引）
- 自动设置 `polymorphic_on='_polymorphic_name'`
- 继承 `ABC` 且有抽象方法时自动设置 `polymorphic_abstract=True`

**关键方法：**

```python
@classmethod
def _is_joined_table_inheritance(cls) -> bool
    # 检查是否为 JTI（子类有独立表返回 True）

@classmethod
def get_concrete_subclasses(cls) -> list[type]
    # 递归获取所有非抽象子类

@classmethod
def get_identity_to_class_map(cls) -> dict[str, type]
    # polymorphic_identity -> 子类映射

@classmethod
def get_polymorphic_discriminator(cls) -> str
    # 返回鉴别列名称
```

### `create_subclass_id_mixin(parent_table_name: str) -> type`

动态创建 JTI 子类 ID Mixin。生成的 Mixin 包含 `id: UUID = Field(foreign_key='{parent_table}.id', primary_key=True)`。

**必须放在继承列表第一位**以正确覆盖 `id` 字段。

### `AutoPolymorphicIdentityMixin`

自动根据类名生成 `polymorphic_identity`。

- 单层：类名小写（`WebSearchTool` -> `"websearchtool"`）
- 嵌套：`{parent_identity}.{classname}`（`Function` -> `"function"`, `CodeInterpreter(Function)` -> `"function.codeinterpreter"`）
- 也处理 STI 子类列注册

### STI 两阶段注册

```python
# 阶段 1：configure_mappers() 之前
register_sti_columns_for_all_subclasses()
# 将子类字段作为 nullable 列添加到父表
# 修复 InstrumentedAttribute 污染的 model_fields
# 重建 Pydantic core schema

# 阶段 2：configure_mappers() 之后
register_sti_column_properties_for_all_subclasses()
# 将列注册为 ColumnProperty 到 mapper
# 注册 StrEnum 字段的 load/refresh 自动转换
```

---

## 乐观锁

### `OptimisticLockMixin`

添加 `version: int = 0` 字段，使用 SQLAlchemy 的 `version_id_col` 机制。

每次 UPDATE 生成：`UPDATE table SET ..., version = version + 1 WHERE id = ? AND version = ?`

### `OptimisticLockError`

| 属性 | 类型 | 说明 |
|------|------|------|
| `model_class` | `str \| None` | 模型类名 |
| `record_id` | `str \| None` | 记录 ID |
| `expected_version` | `int \| None` | 期望版本号 |
| `original_error` | `StaleDataError \| None` | 原始异常 |

---

## 关系预加载

### `@requires_relations(*relations)`

装饰器，声明方法需要的关系并自动加载。

**参数格式：**
- 字符串：本类属性名（`'generator'`）
- `QueryableAttribute`：外部类属性（`Generator.config`，用于嵌套关系）

**行为：**
1. 提取 session（kwargs `'session'` -> 位置参数 -> 任何 AsyncSession 类型的 kwarg）
2. 检查关系加载状态（`sa_inspect(obj).unloaded`）
3. 未加载的关系通过单次 `cls.get()` 查询获取
4. 结果通过 `object.__setattr__` 就地更新

支持普通 async 函数和 async 生成器。元数据 `_required_relations` 存储在 wrapper 上。

### `@requires_for_update`

运行时检查实例是否通过 `get(with_for_update=True)` 获取。不满足时抛出 `RuntimeError`。

元数据 `_requires_for_update = True` 存储在 wrapper 上，供静态分析器使用。

### `RelationPreloadMixin`

提供 `_ensure_relations_loaded()` 和导入时验证。

**`__init_subclass__`：** 在类创建时验证所有 `@requires_relations` 声明的字符串关系名存在。不存在则立即抛出 `AttributeError`。

**手动 API（通常不需要）：**

```python
# 获取方法需要的关系列表
rels = MyClass.get_relations_for_method('calculate_cost')
rels = MyClass.get_relations_for_methods('method1', 'method2')

# 手动预加载
await instance.preload_for(session, 'method1', 'method2')
```

---

## Redis 缓存

### `CachedTableBaseMixin`

双层 Redis 缓存。MRO 中必须在 `UUIDTableBaseMixin` 之前。

```python
pip install sqlmodel-ext[cache]  # redis + orjson

# 启动配置（一次性）
from redis.asyncio import Redis
CachedTableBaseMixin.configure_redis(Redis.from_url("redis://localhost:6379/0", decode_responses=False))

# 定义缓存模型
class Character(CachedTableBaseMixin, CharacterBase, UUIDTableBaseMixin, table=True, cache_ttl=1800):
    pass  # 30 分钟 TTL
```

### 缓存架构

| 层 | Key 格式 | 失效方式 |
|----|---------|---------|
| ID 缓存 | `id:{Model}:{id}` | 行级 DEL（O(1)） |
| 查询缓存 | `query:{Model}:v{version}:{hash}` | 版本号 INCR（O(1)）使旧 key 不可达 |
| 版本号 | `ver:{Model}` | 写入时 INCR |

### 自动失效

- `save()`/`update()`：DELETE `id:{cls}:{id}` + INCR 查询缓存版本号
- `delete(instances)`：每个实例的 ID 缓存 + 查询缓存版本号
- `delete(condition)`：全模型 wipe
- `add()`：仅查询缓存版本号
- STI 子类变更自动级联 bump 所有祖先版本号

### 降级

Redis 不可用时自动回退到数据库查询，记录 WARNING 日志。

### 手动控制

```python
# 跳过缓存直接查 DB（get() 支持 no_cache 参数）
user = await User.get(session, User.id == uid, no_cache=True)

# 手动失效
await User.invalidate_by_id(user_id)
await User.invalidate_all()
```

### Metrics 回调

```python
CachedTableBaseMixin.on_cache_hit = lambda name: metrics.incr(f"cache.hit.{name}")
CachedTableBaseMixin.on_cache_miss = lambda name: metrics.incr(f"cache.miss.{name}")
```

---

## 响应 DTO Mixin

用于 API 响应模型，字段定义为**必填**（从数据库返回时始终有值）。

| Mixin | 字段 |
|-------|------|
| `IntIdInfoMixin` | `id: int` |
| `UUIDIdInfoMixin` | `id: UUID` |
| `DatetimeInfoMixin` | `created_at: datetime`, `updated_at: datetime` |
| `IntIdDatetimeInfoMixin` | `id: int` + timestamps |
| `UUIDIdDatetimeInfoMixin` | `id: UUID` + timestamps |

```python
class UserResponse(UserBase, UUIDIdDatetimeInfoMixin):
    """API 响应 -- id、created_at、updated_at 始终存在"""
    pass
```

---

## 字段类型

### 字符串约束

所有字符串类型均为 `Annotated[str, ...]`，同时设置 Pydantic `max_length` 和 SQLAlchemy `String(length)`。拒绝 null 字节。

### 数值约束

| 类型 | 范围 | SA 类型 | 说明 |
|------|------|--------|------|
| `Port` | 1--65535 | `Integer` | 网络端口 |
| `Percentage` | 0--100 | `Integer` | 百分比 |
| `PositiveInt` | 1--INT32_MAX | `Integer` | 计数、数量 |
| `NonNegativeInt` | 0--INT32_MAX | `Integer` | 索引、计数器 |
| `PositiveBigInt` | 1--JS_MAX_SAFE_INTEGER | `BigInteger` | 大整数（JS 安全） |
| `NonNegativeBigInt` | 0--JS_MAX_SAFE_INTEGER | `BigInteger` | 大整数（JS 安全） |
| `PositiveFloat` | > 0.0 | `Float` | 价格、重量 |
| `NonNegativeFloat` | >= 0.0 | `Float` | 非负浮点 |

### URL 类型

所有 URL 类型均为 `str` 子类，数据库中存储为 VARCHAR，Python 中为普通字符串，通过 `__get_pydantic_core_schema__` 提供 Pydantic 验证。

| 类型 | 协议限制 | SSRF 防护 |
|------|---------|-----------|
| `Url` | 任意 | 无 |
| `HttpUrl` | HTTP/HTTPS | 无 |
| `WebSocketUrl` | WS/WSS | 无 |
| `SafeHttpUrl` | HTTP/HTTPS | 阻止内网/回环/保留 |

**`SafeHttpUrl` 阻止的地址：**
- 回环：`127.x`, `::1`, `localhost`
- 内网：`10.x`, `172.16-31.x`, `192.168.x`
- 链路本地：`169.254.x`, `fe80::/10`
- 保留、多播、未指定地址

```python
from sqlmodel_ext import SafeHttpUrl, UnsafeURLError, validate_not_private_host

# 单独使用验证器
try:
    validate_not_private_host("192.168.1.1")
except UnsafeURLError:
    print("已阻止内网 IP")
```

### `IPAddress`

IPv4/IPv6 地址类型（`str` 子类），存储为 VARCHAR。

```python
server = Server(ip="192.168.1.1")
server.ip.is_private()  # True
```

### 路径类型

| 类型 | 说明 |
|------|------|
| `FilePathType` | 文件路径（必须包含文件名） |
| `DirectoryPathType` | 目录路径（不能包含文件扩展名） |

### `ModuleNameMixin`

多态模型的模块名称 Mixin。

---

## PostgreSQL 类型

位于 `sqlmodel_ext.field_types.dialects.postgresql`，不从顶层包导入。

### `Array[T]` / `Array[T, max_length]`

Python `list[T]` -> PostgreSQL 原生 `ARRAY`。

| Python 类型 | PostgreSQL 类型 |
|-------------|----------------|
| `str` | `TEXT[]` |
| `int` | `INTEGER[]` |
| `dict` | `JSONB[]` |
| `UUID` | `UUID[]` |
| `Enum` 子类 | `ENUM[]` |

```python
tags: Array[str] = Field(default_factory=list)
limited: Array[dict, 20] = Field(default_factory=list)  # Pydantic 验证最多 20 项
```

### `JSON100K` / `JSONList100K`

带 100K 字符输入限制的 JSONB 类型。需要 `orjson`。

| 类型 | Python 类型 | 接受输入 |
|------|-----------|---------|
| `JSON100K` | `dict[str, Any]` | dict 或 JSON 字符串 |
| `JSONList100K` | `list[dict[str, Any]]` | list 或 JSON 字符串 |

### `NumpyVector[dims]` / `NumpyVector[dims, dtype]`

pgvector `Vector` + NumPy `ndarray`。需要 `numpy` + `pgvector`。

```python
embedding: NumpyVector[1024, np.float32] = Field(...)
embedding: NumpyVector[768] = Field(...)  # 默认 float32
```

**支持的输入格式：** `ndarray`, `list/tuple`, base64 字典 (`{"dtype": "float32", "shape": 1024, "data_b64": "..."}`), pgvector 字符串

**向量运算（pgvector 运算符）：**

```python
stmt = select(Model).order_by(Model.embedding.l2_distance(query_vec)).limit(10)
stmt = select(Model).order_by(Model.embedding.cosine_distance(query_vec)).limit(10)
stmt = select(Model).order_by(Model.embedding.max_inner_product(query_vec)).limit(10)
```

**异常层次：**

| 异常 | 说明 |
|------|------|
| `VectorError` | 基类 |
| `VectorDimensionError` | 维度不匹配 |
| `VectorDTypeError` | dtype 转换失败 |
| `VectorDecodeError` | base64/数据库格式解码失败 |

---

## 静态分析器

`RelationLoadChecker`：基于 AST 的静态分析，检测 MissingGreenlet 风险。**实验性功能，默认关闭。**

```python
import sqlmodel_ext.relation_load_checker as rlc

# 方式 1：启动时自动检查
rlc.check_on_startup = True
run_model_checks(SQLModelBase)  # 在 models/__init__.py

# 方式 2：FastAPI 中间件
from sqlmodel_ext import RelationLoadCheckMiddleware
app.add_middleware(RelationLoadCheckMiddleware)

# 方式 3：手动检查
checker = RelationLoadChecker(model_base_class=SQLModelBase)
warnings = checker.check_function(my_func)
```

### 检查规则

| 规则 | 说明 |
|------|------|
| RLC001 | response_model 有关系但端点未加载 |
| RLC002 | save/update 后访问关系但未重新加载 |
| RLC003 | 访问未加载的关系（局部变量） |
| RLC005 | 依赖函数缺少 response_model 需要的关系 |
| RLC007 | commit 后访问列 |
| RLC008 | commit 后调用过期对象的方法 |
| RLC010 | commit 后将过期对象传给函数 |
| RLC011 | 隐式 dunder（`__len__`, `__iter__`）触发关系访问 |
| RLC012 | response_model 有 STI 子类独有列但端点返回基类 |

**限制：** 可能误报；仅分析 async 函数；模块级作用域（未导入的代码跳过）。

---

## 工具函数与异常

### 异常

| 异常 | 说明 |
|------|------|
| `RecordNotFoundError` | `status_code=404`，`get_exist_one` 无 FastAPI 时抛出 |
| `OptimisticLockError` | 乐观锁冲突，含 `model_class`, `record_id`, `expected_version` |
| `UnsafeURLError` | `SafeHttpUrl` 阻止的地址（`ValueError` 子类） |

### 时间工具（`sqlmodel_ext._utils`）

```python
now = lambda: datetime.now(timezone.utc)      # UTC 时间戳
now_date = lambda: datetime.now(timezone.utc).date()  # UTC 日期
```

### 公共 API 导出

所有公共符号从 `sqlmodel_ext` 顶层导出：

```python
from sqlmodel_ext import (
    # 基类
    SQLModelBase, ExtraIgnoreModelBase,
    # 异常
    RecordNotFoundError,
    # 分页
    ListResponse, TimeFilterRequest, PaginationRequest, TableViewRequest,
    # Table Mixin
    SESSION_FOR_UPDATE_KEY, TableBaseMixin, UUIDTableBaseMixin,
    rel, cond, safe_reset,
    # 多态
    PolymorphicBaseMixin, AutoPolymorphicIdentityMixin,
    create_subclass_id_mixin,
    register_sti_columns_for_all_subclasses,
    register_sti_column_properties_for_all_subclasses,
    # 乐观锁
    OptimisticLockMixin, OptimisticLockError,
    # 关系预加载
    RelationPreloadMixin, requires_relations, requires_for_update,
    # Redis 缓存
    CachedTableBaseMixin,
    # 响应 DTO
    IntIdInfoMixin, UUIDIdInfoMixin, DatetimeInfoMixin,
    IntIdDatetimeInfoMixin, UUIDIdDatetimeInfoMixin,
    # 字段类型（字符串）
    Str16, Str24, Str32, Str36, Str48, Str64, Str100, Str128,
    Str255, Str256, Str500, Str512, Str2048,
    Text1K, Text1024, Text2K, Text2500, Text3K, Text5K,
    Text10K, Text32K, Text60K, Text64K, Text100K, Text1M,
    # 字段类型（数值）
    INT32_MAX, INT64_MAX, JS_MAX_SAFE_INTEGER,
    Port, Percentage, PositiveInt, NonNegativeInt,
    PositiveBigInt, NonNegativeBigInt, PositiveFloat, NonNegativeFloat,
    # 字段类型（其他）
    DirectoryPathType, FilePathType,
    IPAddress, Url, HttpUrl, WebSocketUrl, SafeHttpUrl,
    UnsafeURLError, validate_not_private_host, ModuleNameMixin,
    # 静态分析
    RelationLoadChecker, RelationLoadWarning,
    RelationLoadCheckMiddleware, run_model_checks, mark_app_check_completed,
)
```

### 架构

```
sqlmodel_ext/
    __init__.py              # 公共 API 重导出
    base.py                  # SQLModelBase + __DeclarativeMeta 元类
    _compat.py               # Python 3.14 (PEP 649) 猴子补丁
    _sa_type.py              # 从 Annotated 元数据提取 sa_type
    _utils.py                # now()、now_date() 时间戳工具
    _exceptions.py           # RecordNotFoundError
    pagination.py            # ListResponse、请求模型
    relation_load_checker.py # AST 静态分析器（~2000 行）
    mixins/
        table.py             # TableBaseMixin、UUIDTableBaseMixin（异步 CRUD）
        cached_table.py      # CachedTableBaseMixin（Redis 缓存）
        polymorphic.py       # 多态继承支持
        optimistic_lock.py   # 乐观锁
        relation_preload.py  # 关系预加载装饰器
        info_response.py     # 响应 DTO Mixin
    field_types/
        __init__.py          # 字段类型定义与导出
        _ssrf.py             # SSRF 防护
        ip_address.py        # IPAddress 类型
        url.py               # URL 类型
        _internal/path.py    # 路径类型
        mixins/              # ModuleNameMixin
        dialects/postgresql/ # PostgreSQL 特有类型
            array.py         # Array[T]
            jsonb_types.py   # JSON100K、JSONList100K
            numpy_vector.py  # NumpyVector[dims, dtype]
            exceptions.py    # Vector 异常
```
