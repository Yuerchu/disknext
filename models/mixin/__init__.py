"""
SQLModel Mixin模块

提供各种Mixin类供SQLModel实体使用。

包含：
- polymorphic: 联表继承工具（create_subclass_id_mixin, AutoPolymorphicIdentityMixin, PolymorphicBaseMixin）
- table: 表基类（TableBaseMixin, UUIDTableBaseMixin）
- table: 查询参数类（TimeFilterRequest, PaginationRequest, TableViewRequest）
- jwt/: JWT认证相关（JWTAuthMixin, JWTManager, JWTKey等）- 需要时直接从 .jwt 导入
- info_response: InfoResponse DTO的id/时间戳Mixin

导入顺序很重要，避免循环导入：
1. polymorphic（只依赖 SQLModelBase）
2. table（依赖 polymorphic）

注意：jwt 模块不在此处导入，因为 jwt/manager.py 导入 ServerConfig，
而 ServerConfig 导入本模块，会形成循环。需要 jwt 功能时请直接从 .jwt 导入。
"""
# polymorphic 必须先导入
from .polymorphic import (
    create_subclass_id_mixin,
    AutoPolymorphicIdentityMixin,
    PolymorphicBaseMixin,
)
# table 依赖 polymorphic
from .table import (
    TableBaseMixin,
    UUIDTableBaseMixin,
    TimeFilterRequest,
    PaginationRequest,
    TableViewRequest,
    ListResponse,
    T,
    now,
    now_date,
)
# jwt 不在此处导入（避免循环：jwt/manager.py → ServerConfig → mixin → jwt）
# 需要时直接从 sqlmodels.mixin.jwt 导入
from .info_response import (
    IntIdInfoMixin,
    UUIDIdInfoMixin,
    DatetimeInfoMixin,
    IntIdDatetimeInfoMixin,
    UUIDIdDatetimeInfoMixin,
)
