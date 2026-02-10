"""
SQLModel Mixin模块

提供各种Mixin类供SQLModel实体使用。

包含：
- polymorphic: 联表继承工具（create_subclass_id_mixin, AutoPolymorphicIdentityMixin, PolymorphicBaseMixin）
- optimistic_lock: 乐观锁（OptimisticLockMixin, OptimisticLockError）
- table: 表基类（TableBaseMixin, UUIDTableBaseMixin）
- table: 查询参数类（TimeFilterRequest, PaginationRequest, TableViewRequest）
- relation_preload: 关系预加载（RelationPreloadMixin, requires_relations）
- jwt/: JWT认证相关（JWTAuthMixin, JWTManager, JWTKey等）- 需要时直接从 .jwt 导入
- info_response: InfoResponse DTO的id/时间戳Mixin

导入顺序很重要，避免循环导入：
1. polymorphic（只依赖 SQLModelBase）
2. optimistic_lock（只依赖 SQLAlchemy）
3. table（依赖 polymorphic 和 optimistic_lock）
4. relation_preload（只依赖 SQLModelBase）

注意：jwt 模块不在此处导入，因为 jwt/manager.py 导入 ServerConfig，
而 ServerConfig 导入本模块，会形成循环。需要 jwt 功能时请直接从 .jwt 导入。
"""
# polymorphic 必须先导入
from .polymorphic import (
    AutoPolymorphicIdentityMixin,
    PolymorphicBaseMixin,
    create_subclass_id_mixin,
    register_sti_column_properties_for_all_subclasses,
    register_sti_columns_for_all_subclasses,
)
# optimistic_lock 只依赖 SQLAlchemy，必须在 table 之前
from .optimistic_lock import (
    OptimisticLockError,
    OptimisticLockMixin,
)
# table 依赖 polymorphic 和 optimistic_lock
from .table import (
    ListResponse,
    PaginationRequest,
    T,
    TableBaseMixin,
    TableViewRequest,
    TimeFilterRequest,
    UUIDTableBaseMixin,
    now,
    now_date,
)
# relation_preload 只依赖 SQLModelBase
from .relation_preload import (
    RelationPreloadMixin,
    requires_relations,
)
# jwt 不在此处导入（避免循环：jwt/manager.py → ServerConfig → mixin → jwt）
# 需要时直接从 sqlmodels.mixin.jwt 导入
from .info_response import (
    DatetimeInfoMixin,
    IntIdDatetimeInfoMixin,
    IntIdInfoMixin,
    UUIDIdDatetimeInfoMixin,
    UUIDIdInfoMixin,
)
