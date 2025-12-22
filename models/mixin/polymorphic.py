"""
联表继承（Joined Table Inheritance）的通用工具

提供用于简化SQLModel多态表设计的辅助函数和Mixin。

Usage Example:

    from sqlmodels.base import SQLModelBase
    from sqlmodels.mixin import UUIDTableBaseMixin
    from sqlmodels.mixin.polymorphic import (
        PolymorphicBaseMixin,
        create_subclass_id_mixin,
        AutoPolymorphicIdentityMixin
    )

    # 1. 定义Base类（只有字段，无表）
    class ASRBase(SQLModelBase):
        name: str
        \"\"\"配置名称\"\"\"

        base_url: str
        \"\"\"服务地址\"\"\"

    # 2. 定义抽象父类（有表），使用 PolymorphicBaseMixin
    class ASR(
        ASRBase,
        UUIDTableBaseMixin,
        PolymorphicBaseMixin,
        ABC
    ):
        \"\"\"ASR配置的抽象基类\"\"\"
        # PolymorphicBaseMixin 自动提供:
        # - _polymorphic_name 字段
        # - polymorphic_on='_polymorphic_name'
        # - polymorphic_abstract=True（当有抽象方法时）

    # 3. 为第二层子类创建ID Mixin
    ASRSubclassIdMixin = create_subclass_id_mixin('asr')

    # 4. 创建第二层抽象类（如果需要）
    class FunASR(
        ASRSubclassIdMixin,
        ASR,
        AutoPolymorphicIdentityMixin,
        polymorphic_abstract=True
    ):
        \"\"\"FunASR的抽象基类，可能有多个实现\"\"\"
        pass

    # 5. 创建具体实现类
    class FunASRLocal(FunASR, table=True):
        \"\"\"FunASR本地部署版本\"\"\"
        # polymorphic_identity 会自动设置为 'asr.funasrlocal'
        pass

    # 6. 获取所有具体子类（用于 selectin_polymorphic）
    concrete_asrs = ASR.get_concrete_subclasses()
    # 返回 [FunASRLocal, ...]
"""
import uuid
from abc import ABC
from uuid import UUID

from pydantic.fields import FieldInfo
from pydantic_core import PydanticUndefined
from sqlalchemy import String, inspect
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.orm.attributes import InstrumentedAttribute
from sqlmodel import Field

from models.base.sqlmodel_base import SQLModelBase


def create_subclass_id_mixin(parent_table_name: str) -> type['SQLModelBase']:
    """
    动态创建SubclassIdMixin类

    在联表继承中，子类需要一个外键指向父表的主键。
    此函数生成一个Mixin类，提供这个外键字段，并自动生成UUID。

    Args:
        parent_table_name: 父表名称（如'asr', 'tts', 'tool', 'function'）

    Returns:
        一个Mixin类，包含id字段（外键 + 主键 + default_factory=uuid.uuid4）

    Example:
        >>> ASRSubclassIdMixin = create_subclass_id_mixin('asr')
        >>> class FunASR(ASRSubclassIdMixin, ASR, table=True):
        ...     pass

    Note:
        - 生成的Mixin应该放在继承列表的第一位，确保通过MRO覆盖UUIDTableBaseMixin的id
        - 生成的类名为 {ParentTableName}SubclassIdMixin（PascalCase）
        - 本项目所有联表继承均使用UUID主键（UUIDTableBaseMixin）
    """
    if not parent_table_name:
        raise ValueError("parent_table_name 不能为空")

    # 转换为PascalCase作为类名
    class_name_parts = parent_table_name.split('_')
    class_name = ''.join(part.capitalize() for part in class_name_parts) + 'SubclassIdMixin'

    # 使用闭包捕获parent_table_name
    _parent_table_name = parent_table_name

    # 创建带有__init_subclass__的mixin类，用于在子类定义后修复model_fields
    class SubclassIdMixin(SQLModelBase):
        # 定义id字段
        id: UUID = Field(
            default_factory=uuid.uuid4,
            foreign_key=f'{_parent_table_name}.id',
            primary_key=True,
        )

        @classmethod
        def __pydantic_init_subclass__(cls, **kwargs):
            """
            Pydantic v2 的子类初始化钩子，在模型完全构建后调用

            修复联表继承中子类字段的default_factory丢失问题。
            SQLAlchemy 的 InstrumentedAttribute 会污染从父类继承的字段，
            导致 INSERT 语句中出现 `table.column` 引用而非实际值。

            通过从 MRO 中查找父类的原始字段定义来获取正确的 default_factory，
            遵循单一真相原则（不硬编码 default_factory）。

            需要修复的字段：
            - id: 主键（从父类获取 default_factory）
            - created_at: 创建时间戳（从父类获取 default_factory）
            - updated_at: 更新时间戳（从父类获取 default_factory）
            """
            super().__pydantic_init_subclass__(**kwargs)

            if not hasattr(cls, 'model_fields'):
                return

            def find_original_field_info(field_name: str) -> FieldInfo | None:
                """从 MRO 中查找字段的原始定义（未被 InstrumentedAttribute 污染的）"""
                for base in cls.__mro__[1:]:  # 跳过自己
                    if hasattr(base, 'model_fields') and field_name in base.model_fields:
                        field_info = base.model_fields[field_name]
                        # 跳过被 InstrumentedAttribute 污染的
                        if not isinstance(field_info.default, InstrumentedAttribute):
                            return field_info
                return None

            # 动态检测所有需要修复的字段
            # 遵循单一真相原则：不硬编码字段列表，而是通过以下条件判断：
            # 1. default 是 InstrumentedAttribute（被 SQLAlchemy 污染）
            # 2. 原始定义有 default_factory 或明确的 default 值
            #
            # 覆盖场景：
            # - UUID主键（UUIDTableBaseMixin）：id 有 default_factory=uuid.uuid4，需要修复
            # - int主键（TableBaseMixin）：id 用 default=None，不需要修复（数据库自增）
            # - created_at/updated_at：有 default_factory=now，需要修复
            # - 外键字段（created_by_id等）：有 default=None，需要修复
            # - 普通字段（name, temperature等）：无 default_factory，不需要修复
            #
            # MRO 查找保证：
            # - 在多重继承场景下，MRO 顺序是确定性的
            # - find_original_field_info 会找到第一个未被污染且有该字段的父类
            for field_name, current_field in cls.model_fields.items():
                # 检查是否被污染（default 是 InstrumentedAttribute）
                if not isinstance(current_field.default, InstrumentedAttribute):
                    continue  # 未被污染，跳过

                # 从父类查找原始定义
                original = find_original_field_info(field_name)
                if original is None:
                    continue  # 找不到原始定义，跳过

                # 根据原始定义的 default/default_factory 来修复
                if original.default_factory:
                    # 有 default_factory（如 uuid.uuid4, now）
                    new_field = FieldInfo(
                        default_factory=original.default_factory,
                        annotation=current_field.annotation,
                        json_schema_extra=current_field.json_schema_extra,
                    )
                elif original.default is not PydanticUndefined:
                    # 有明确的 default 值（如 None, 0, ""），且不是 PydanticUndefined
                    # PydanticUndefined 表示字段没有默认值（必填）
                    new_field = FieldInfo(
                        default=original.default,
                        annotation=current_field.annotation,
                        json_schema_extra=current_field.json_schema_extra,
                    )
                else:
                    continue  # 既没有 default_factory 也没有有效的 default，跳过

                # 复制SQLModel特有的属性
                if hasattr(current_field, 'foreign_key'):
                    new_field.foreign_key = current_field.foreign_key
                if hasattr(current_field, 'primary_key'):
                    new_field.primary_key = current_field.primary_key

                cls.model_fields[field_name] = new_field

    # 设置类名和文档
    SubclassIdMixin.__name__ = class_name
    SubclassIdMixin.__qualname__ = class_name
    SubclassIdMixin.__doc__ = f"""
    {parent_table_name}子类的ID Mixin

    用于{parent_table_name}的子类，提供外键指向父表。
    通过MRO确保此id字段覆盖继承的id字段。
    """

    return SubclassIdMixin


class AutoPolymorphicIdentityMixin:
    """
    自动生成polymorphic_identity的Mixin

    使用此Mixin的类会自动根据类名生成polymorphic_identity。
    格式：{parent_polymorphic_identity}.{classname_lowercase}

    如果没有父类的polymorphic_identity，则直接使用类名小写。

    Example:
        >>> class Tool(UUIDTableBaseMixin, polymorphic_on='__polymorphic_name', polymorphic_abstract=True):
        ...     __polymorphic_name: str
        ...
        >>> class Function(Tool, AutoPolymorphicIdentityMixin, polymorphic_abstract=True):
        ...     pass
        ...     # polymorphic_identity 会自动设置为 'function'
        ...
        >>> class CodeInterpreterFunction(Function, table=True):
        ...     pass
        ...     # polymorphic_identity 会自动设置为 'function.codeinterpreterfunction'

    Note:
        - 如果手动在__mapper_args__中指定了polymorphic_identity，会被保留
        - 此Mixin应该在继承列表中靠后的位置（在表基类之前）
    """

    def __init_subclass__(cls, polymorphic_identity: str | None = None, **kwargs):
        """
        子类化钩子，自动生成polymorphic_identity

        Args:
            polymorphic_identity: 如果手动指定，则使用指定的值
            **kwargs: 其他SQLModel参数（如table=True, polymorphic_abstract=True）
        """
        super().__init_subclass__(**kwargs)

        # 如果手动指定了polymorphic_identity，使用指定的值
        if polymorphic_identity is not None:
            identity = polymorphic_identity
        else:
            # 自动生成polymorphic_identity
            class_name = cls.__name__.lower()

            # 尝试从父类获取polymorphic_identity作为前缀
            parent_identity = None
            for base in cls.__mro__[1:]:  # 跳过自己
                if hasattr(base, '__mapper_args__') and isinstance(base.__mapper_args__, dict):
                    parent_identity = base.__mapper_args__.get('polymorphic_identity')
                    if parent_identity:
                        break

            # 构建identity
            if parent_identity:
                identity = f'{parent_identity}.{class_name}'
            else:
                identity = class_name

        # 设置到__mapper_args__
        if '__mapper_args__' not in cls.__dict__:
            cls.__mapper_args__ = {}

        # 只在尚未设置polymorphic_identity时设置
        if 'polymorphic_identity' not in cls.__mapper_args__:
            cls.__mapper_args__['polymorphic_identity'] = identity


class PolymorphicBaseMixin:
    """
    为联表继承链中的基类自动配置 polymorphic 设置的 Mixin

    此 Mixin 自动设置以下内容：
    - `polymorphic_on='_polymorphic_name'`: 使用 _polymorphic_name 字段作为多态鉴别器
    - `_polymorphic_name: str`: 定义多态鉴别器字段（带索引）
    - `polymorphic_abstract=True`: 当类继承自 ABC 且有抽象方法时，自动标记为抽象类

    使用场景：
        适用于需要 joined table inheritance 的基类，例如 Tool、ASR、TTS 等。

    用法示例：
        ```python
        from abc import ABC
        from sqlmodels.mixin import UUIDTableBaseMixin
        from sqlmodels.mixin.polymorphic import PolymorphicBaseMixin

        # 定义基类
        class MyTool(UUIDTableBaseMixin, PolymorphicBaseMixin, ABC):
            __tablename__ = 'mytool'

            # 不需要手动定义 _polymorphic_name
            # 不需要手动设置 polymorphic_on
            # 不需要手动设置 polymorphic_abstract

        # 定义子类
        class SpecificTool(MyTool):
            __tablename__ = 'specifictool'

            # 会自动继承 polymorphic 配置
        ```

    自动行为：
        1. 定义 `_polymorphic_name: str` 字段（带索引）
        2. 设置 `__mapper_args__['polymorphic_on'] = '_polymorphic_name'`
        3. 自动检测抽象类：
           - 如果类继承了 ABC 且有未实现的抽象方法，设置 polymorphic_abstract=True
           - 否则设置为 False

    手动覆盖：
        可以在类定义时手动指定参数来覆盖自动行为：
        ```python
        class MyTool(
            UUIDTableBaseMixin,
            PolymorphicBaseMixin,
            ABC,
            polymorphic_on='custom_field',  # 覆盖默认的 _polymorphic_name
            polymorphic_abstract=False       # 强制不设为抽象类
        ):
            pass
        ```

    注意事项：
        - 此 Mixin 应该与 UUIDTableBaseMixin 或 TableBaseMixin 配合使用
        - 适用于联表继承（joined table inheritance）场景
        - 子类会自动继承 _polymorphic_name 字段定义
        - 使用单下划线前缀是因为：
          * SQLAlchemy 会映射单下划线字段为数据库列
          * Pydantic 将其视为私有属性，不参与序列化
          * 双下划线字段会被 SQLAlchemy 排除，不映射为数据库列
    """

    # 定义 _polymorphic_name 字段，所有使用此 mixin 的类都会有这个字段
    #
    # 设计选择：使用单下划线前缀 + Mapped[str] + mapped_column
    #
    # 为什么这样做：
    # 1. 单下划线前缀表示"内部实现细节"，防止外部通过 API 直接修改
    # 2. Mapped + mapped_column 绕过 Pydantic v2 的字段名限制（不允许下划线前缀）
    # 3. 字段仍然被 SQLAlchemy 映射到数据库，供多态查询使用
    # 4. 字段不出现在 Pydantic 序列化中（model_dump() 和 JSON schema）
    # 5. 内部代码仍然可以正常访问和修改此字段
    #
    # 详细说明请参考：sqlmodels/base/POLYMORPHIC_NAME_DESIGN.md
    _polymorphic_name: Mapped[str] = mapped_column(String, index=True)
    """
    多态鉴别器字段，用于标识具体的子类类型

    注意：此字段使用单下划线前缀，表示内部使用。
    - ✅ 存储到数据库
    - ✅ 不出现在 API 序列化中
    - ✅ 防止外部直接修改
    """

    def __init_subclass__(
        cls,
        polymorphic_on: str | None = None,
        polymorphic_abstract: bool | None = None,
        **kwargs
    ):
        """
        在子类定义时自动配置 polymorphic 设置

        Args:
            polymorphic_on: polymorphic_on 字段名，默认为 '_polymorphic_name'。
                           设置为其他值可以使用不同的字段作为多态鉴别器。
            polymorphic_abstract: 是否为抽象类。
                                 - None: 自动检测（默认）
                                 - True: 强制设为抽象类
                                 - False: 强制设为非抽象类
            **kwargs: 传递给父类的其他参数
        """
        super().__init_subclass__(**kwargs)

        # 初始化 __mapper_args__（如果还没有）
        if '__mapper_args__' not in cls.__dict__:
            cls.__mapper_args__ = {}

        # 设置 polymorphic_on（默认为 _polymorphic_name）
        if 'polymorphic_on' not in cls.__mapper_args__:
            cls.__mapper_args__['polymorphic_on'] = polymorphic_on or '_polymorphic_name'

        # 自动检测或设置 polymorphic_abstract
        if 'polymorphic_abstract' not in cls.__mapper_args__:
            if polymorphic_abstract is None:
                # 自动检测：如果继承了 ABC 且有抽象方法，则为抽象类
                has_abc = ABC in cls.__mro__
                has_abstract_methods = bool(getattr(cls, '__abstractmethods__', set()))
                polymorphic_abstract = has_abc and has_abstract_methods

            cls.__mapper_args__['polymorphic_abstract'] = polymorphic_abstract

    @classmethod
    def get_concrete_subclasses(cls) -> list[type['PolymorphicBaseMixin']]:
        """
        递归获取当前类的所有具体（非抽象）子类

        用于 selectin_polymorphic 加载策略，自动检测联表继承的所有具体子类。
        可在任意多态基类上调用，返回该类的所有非抽象子类。

        :return: 所有具体子类的列表（不包含 polymorphic_abstract=True 的抽象类）
        """
        result: list[type[PolymorphicBaseMixin]] = []
        for subclass in cls.__subclasses__():
            # 使用 inspect() 获取 mapper 的公开属性
            # 源码确认: mapper.polymorphic_abstract 是公开属性 (mapper.py:811)
            mapper = inspect(subclass)
            if not mapper.polymorphic_abstract:
                result.append(subclass)
            # 无论是否抽象，都需要递归（抽象类可能有具体子类）
            if hasattr(subclass, 'get_concrete_subclasses'):
                result.extend(subclass.get_concrete_subclasses())
        return result

    @classmethod
    def get_polymorphic_discriminator(cls) -> str:
        """
        获取多态鉴别字段名

        使用 SQLAlchemy inspect 从 mapper 获取，支持从子类调用。

        :return: 多态鉴别字段名（如 '_polymorphic_name'）
        :raises ValueError: 如果类未配置 polymorphic_on
        """
        polymorphic_on = inspect(cls).polymorphic_on
        if polymorphic_on is None:
            raise ValueError(
                f"{cls.__name__} 未配置 polymorphic_on，"
                f"请确保正确继承 PolymorphicBaseMixin"
            )
        return polymorphic_on.key

    @classmethod
    def get_identity_to_class_map(cls) -> dict[str, type['PolymorphicBaseMixin']]:
        """
        获取 polymorphic_identity 到具体子类的映射

        包含所有层级的具体子类（如 Function 和 ModelSwitchFunction 都会被包含）。

        :return: identity 到子类的映射字典
        """
        result: dict[str, type[PolymorphicBaseMixin]] = {}
        for subclass in cls.get_concrete_subclasses():
            identity = inspect(subclass).polymorphic_identity
            if identity:
                result[identity] = subclass
        return result
