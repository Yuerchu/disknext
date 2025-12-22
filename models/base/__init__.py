"""
SQLModel 基础模块

包含：
- SQLModelBase: 所有 SQLModel 类的基类（真正的基类）

注意：
    TableBase, UUIDTableBase, PolymorphicBaseMixin 已迁移到 models.mixin
    为了避免循环导入，此处不再重新导出它们
    请直接从 models.mixin 导入这些类
"""
from .sqlmodel_base import SQLModelBase
