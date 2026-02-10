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

from loguru import logger as l
from pydantic.fields import FieldInfo
from pydantic_core import PydanticUndefined
from sqlalchemy import Column, String, inspect
from sqlalchemy.orm import ColumnProperty, Mapped, mapped_column
from sqlalchemy.orm.attributes import InstrumentedAttribute
from sqlmodel import Field
from sqlmodel.main import get_column_from_field

from sqlmodels.base.sqlmodel_base import SQLModelBase

# 用于延迟注册 STI 子类列的队列
# 在所有模型加载完成后，调用 register_sti_columns_for_all_subclasses() 处理
_sti_subclasses_to_register: list[type] = []


def register_sti_columns_for_all_subclasses() -> None:
    """
    为所有已注册的 STI 子类执行列注册（第一阶段：添加列到表）

    此函数应在 configure_mappers() 之前调用。
    将 STI 子类的字段添加到父表的 metadata 中。
    同时修复被 Column 对象污染的 model_fields。
    """
    for cls in _sti_subclasses_to_register:
        try:
            cls._register_sti_columns()
        except Exception as e:
            l.warning(f"注册 STI 子类 {cls.__name__} 的列时出错: {e}")

        # 修复被 Column 对象污染的 model_fields
        # 必须在列注册后立即修复，因为 Column 污染在类定义时就已发生
        try:
            _fix_polluted_model_fields(cls)
        except Exception as e:
            l.warning(f"修复 STI 子类 {cls.__name__} 的 model_fields 时出错: {e}")


def register_sti_column_properties_for_all_subclasses() -> None:
    """
    为所有已注册的 STI 子类添加列属性到 mapper（第二阶段）

    此函数应在 configure_mappers() 之后调用。
    将 STI 子类的字段作为 ColumnProperty 添加到 mapper 中。
    """
    for cls in _sti_subclasses_to_register:
        try:
            cls._register_sti_column_properties()
        except Exception as e:
            l.warning(f"注册 STI 子类 {cls.__name__} 的列属性时出错: {e}")

    # 清空队列
    _sti_subclasses_to_register.clear()


def _fix_polluted_model_fields(cls: type) -> None:
    """
    修复被 SQLAlchemy InstrumentedAttribute 或 Column 污染的 model_fields

    当 SQLModel 类继承有表的父类时，SQLAlchemy 会在类上创建 InstrumentedAttribute
    或 Column 对象替换原始的字段默认值。这会导致 Pydantic 在构建子类 model_fields
    时错误地使用这些 SQLAlchemy 对象作为默认值。

    此函数从 MRO 中查找原始的字段定义，并修复被污染的 model_fields。

    :param cls: 要修复的类
    """
    if not hasattr(cls, 'model_fields'):
        return

    def find_original_field_info(field_name: str) -> FieldInfo | None:
        """从 MRO 中查找字段的原始定义（未被污染的）"""
        for base in cls.__mro__[1:]:  # 跳过自己
            if hasattr(base, 'model_fields') and field_name in base.model_fields:
                field_info = base.model_fields[field_name]
                # 跳过被 InstrumentedAttribute 或 Column 污染的
                if not isinstance(field_info.default, (InstrumentedAttribute, Column)):
                    return field_info
        return None

    for field_name, current_field in cls.model_fields.items():
        # 检查是否被污染（default 是 InstrumentedAttribute 或 Column）
        # Column 污染发生在 STI 继承链中：当 FunctionBase.show_arguments = True
        # 被继承到有表的子类时，SQLModel 会创建一个 Column 对象替换原始默认值
        if not isinstance(current_field.default, (InstrumentedAttribute, Column)):
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
            # 有明确的 default 值（如 None, 0, True），且不是 PydanticUndefined
            # PydanticUndefined 表示字段没有默认值（必填）
            new_field = FieldInfo(
                default=original.default,
                annotation=current_field.annotation,
                json_schema_extra=current_field.json_schema_extra,
            )
        else:
            continue  # 既没有 default_factory 也没有有效的 default，跳过

        # 复制 SQLModel 特有的属性
        if hasattr(current_field, 'foreign_key'):
            new_field.foreign_key = current_field.foreign_key
        if hasattr(current_field, 'primary_key'):
            new_field.primary_key = current_field.primary_key

        cls.model_fields[field_name] = new_field


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

            修复联表继承中子类字段的 default_factory 丢失问题。
            SQLAlchemy 的 InstrumentedAttribute 或 Column 会污染从父类继承的字段，
            导致 INSERT 语句中出现 `table.column` 引用而非实际值。
            """
            super().__pydantic_init_subclass__(**kwargs)
            _fix_polluted_model_fields(cls)

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
    自动生成polymorphic_identity的Mixin，并支持STI子类列注册

    使用此Mixin的类会自动根据类名生成polymorphic_identity。
    格式：{parent_polymorphic_identity}.{classname_lowercase}

    如果没有父类的polymorphic_identity，则直接使用类名小写。

    **重要：数据库迁移注意事项**

    编写数据迁移脚本时，必须使用完整的 polymorphic_identity 格式，包括父类前缀！

    例如，对于以下继承链::

        LLM (polymorphic_on='_polymorphic_name')
        └── AnthropicCompatibleLLM (polymorphic_identity='anthropiccompatiblellm')
            └── TuziAnthropicLLM (polymorphic_identity='anthropiccompatiblellm.tuzianthropicllm')

    迁移脚本中设置 _polymorphic_name 时::

        # ❌ 错误：缺少父类前缀
        UPDATE llm SET _polymorphic_name = 'tuzianthropicllm' WHERE id = :id

        # ✅ 正确：包含完整的继承链前缀
        UPDATE llm SET _polymorphic_name = 'anthropiccompatiblellm.tuzianthropicllm' WHERE id = :id

    **STI（单表继承）支持**：
    当子类与父类共用同一张表（STI模式）时，此Mixin会自动将子类的新字段
    添加到父表的列定义中。这解决了SQLModel在STI模式下子类字段不被
    注册到父表的问题。

    Example (JTI):
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

    Example (STI):
        >>> class UserFile(UUIDTableBaseMixin, PolymorphicBaseMixin, table=True, polymorphic_abstract=True):
        ...     user_id: UUID
        ...
        >>> class PendingFile(UserFile, AutoPolymorphicIdentityMixin, table=True):
        ...     upload_deadline: datetime | None = None  # 自动添加到 userfile 表
        ...     # polymorphic_identity 会自动设置为 'pendingfile'

    Note:
        - 如果手动在__mapper_args__中指定了polymorphic_identity，会被保留
        - 此Mixin应该在继承列表中靠后的位置（在表基类之前）
        - STI模式下，新字段会在类定义时自动添加到父表的metadata中
    """

    def __init_subclass__(cls, polymorphic_identity: str | None = None, **kwargs):
        """
        子类化钩子，自动生成polymorphic_identity并处理STI列注册

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

        # 注册 STI 子类列的延迟执行
        # 由于 __init_subclass__ 在类定义过程中被调用，此时 model_fields 还不完整
        # 需要在模块加载完成后调用 register_sti_columns_for_all_subclasses()
        _sti_subclasses_to_register.append(cls)

    @classmethod
    def __pydantic_init_subclass__(cls, **kwargs):
        """
        Pydantic v2 的子类初始化钩子，在模型完全构建后调用

        修复 STI 继承中子类字段被 Column 对象污染的问题。
        当 FunctionBase.show_arguments = True 等字段被继承到有表的子类时，
        SQLModel 会创建一个 Column 对象替换原始默认值，导致实例化时字段值不正确。
        """
        super().__pydantic_init_subclass__(**kwargs)
        _fix_polluted_model_fields(cls)

    @classmethod
    def _register_sti_columns(cls) -> None:
        """
        将STI子类的新字段注册到父表的列定义中

        检测当前类是否是STI子类（与父类共用同一张表），
        如果是，则将子类定义的新字段添加到父表的metadata中。

        JTI（联表继承）类会被自动跳过，因为它们有自己独立的表。
        """
        # 查找父表（在 MRO 中找到第一个有 __table__ 的父类）
        parent_table = None
        parent_fields: set[str] = set()

        for base in cls.__mro__[1:]:
            if hasattr(base, '__table__') and base.__table__ is not None:
                parent_table = base.__table__
                # 收集父类的所有字段名
                if hasattr(base, 'model_fields'):
                    parent_fields.update(base.model_fields.keys())
                break

        if parent_table is None:
            return  # 没有找到父表，可能是根类

        # JTI 检测：如果当前类有自己的表且与父表不同，则是 JTI
        # JTI 类有自己独立的表，不需要将列注册到父表
        if hasattr(cls, '__table__') and cls.__table__ is not None:
            if cls.__table__.name != parent_table.name:
                return  # JTI，跳过 STI 列注册

        # 获取当前类的新字段（不在父类中的字段）
        if not hasattr(cls, 'model_fields'):
            return

        existing_columns = {col.name for col in parent_table.columns}

        for field_name, field_info in cls.model_fields.items():
            # 跳过从父类继承的字段
            if field_name in parent_fields:
                continue

            # 跳过私有字段和ClassVar
            if field_name.startswith('_'):
                continue

            # 跳过已存在的列
            if field_name in existing_columns:
                continue

            # 使用 SQLModel 的内置 API 创建列
            try:
                column = get_column_from_field(field_info)
                column.name = field_name
                column.key = field_name
                # STI子类字段在数据库层面必须可空，因为其他子类的行不会有这些字段的值
                # Pydantic层面的约束仍然有效（创建特定子类时会验证必填字段）
                column.nullable = True

                # 将列添加到父表
                parent_table.append_column(column)
            except Exception as e:
                l.warning(f"为 {cls.__name__} 创建列 {field_name} 失败: {e}")

    @classmethod
    def _register_sti_column_properties(cls) -> None:
        """
        将 STI 子类的列作为 ColumnProperty 添加到 mapper

        此方法在 configure_mappers() 之后调用，将已添加到表中的列
        注册为 mapper 的属性，使 ORM 查询能正确识别这些列。

        **重要**：子类的列属性会同时注册到子类和父类的 mapper 上。
        这确保了查询父类时，SELECT 语句包含所有 STI 子类的列，
        避免在响应序列化时触发懒加载（MissingGreenlet 错误）。

        JTI（联表继承）类会被自动跳过，因为它们有自己独立的表。
        """
        # 查找父表和父类（在 MRO 中找到第一个有 __table__ 的父类）
        parent_table = None
        parent_class = None
        for base in cls.__mro__[1:]:
            if hasattr(base, '__table__') and base.__table__ is not None:
                parent_table = base.__table__
                parent_class = base
                break

        if parent_table is None:
            return  # 没有找到父表，可能是根类

        # JTI 检测：如果当前类有自己的表且与父表不同，则是 JTI
        # JTI 类有自己独立的表，不需要将列属性注册到 mapper
        if hasattr(cls, '__table__') and cls.__table__ is not None:
            if cls.__table__.name != parent_table.name:
                return  # JTI，跳过 STI 列属性注册

        # 获取子类和父类的 mapper
        child_mapper = inspect(cls).mapper
        parent_mapper = inspect(parent_class).mapper
        local_table = child_mapper.local_table

        # 查找父类的所有字段名
        parent_fields: set[str] = set()
        if hasattr(parent_class, 'model_fields'):
            parent_fields.update(parent_class.model_fields.keys())

        if not hasattr(cls, 'model_fields'):
            return

        # 获取两个 mapper 已有的列属性
        child_existing_props = {p.key for p in child_mapper.column_attrs}
        parent_existing_props = {p.key for p in parent_mapper.column_attrs}

        for field_name in cls.model_fields:
            # 跳过从父类继承的字段
            if field_name in parent_fields:
                continue

            # 跳过私有字段
            if field_name.startswith('_'):
                continue

            # 检查表中是否有这个列
            if field_name not in local_table.columns:
                continue

            column = local_table.columns[field_name]

            # 添加到子类的 mapper（如果尚不存在）
            if field_name not in child_existing_props:
                try:
                    prop = ColumnProperty(column)
                    child_mapper.add_property(field_name, prop)
                except Exception as e:
                    l.warning(f"为 {cls.__name__} 添加列属性 {field_name} 失败: {e}")

            # 同时添加到父类的 mapper（确保查询父类时 SELECT 包含所有 STI 子类的列）
            if field_name not in parent_existing_props:
                try:
                    prop = ColumnProperty(column)
                    parent_mapper.add_property(field_name, prop)
                except Exception as e:
                    l.warning(f"为父类 {parent_class.__name__} 添加子类 {cls.__name__} 的列属性 {field_name} 失败: {e}")


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
    def _is_joined_table_inheritance(cls) -> bool:
        """
        检测当前类是否使用联表继承（Joined Table Inheritance）

        通过检查子类是否有独立的表来判断：
        - JTI: 子类有独立的 local_table（与父类不同）
        - STI: 子类与父类共用同一个 local_table

        :return: True 表示 JTI，False 表示 STI 或无子类
        """
        mapper = inspect(cls)
        base_table_name = mapper.local_table.name

        # 检查所有直接子类
        for subclass in cls.__subclasses__():
            sub_mapper = inspect(subclass)
            # 如果任何子类有不同的表名，说明是 JTI
            if sub_mapper.local_table.name != base_table_name:
                return True

        return False

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
