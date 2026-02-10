import sys
import typing
from typing import Any, Mapping, get_args, get_origin, get_type_hints

from pydantic import ConfigDict
from pydantic.fields import FieldInfo
from pydantic_core import PydanticUndefined as Undefined
from sqlalchemy.orm import Mapped
from sqlmodel import Field, SQLModel
from sqlmodel.main import SQLModelMetaclass

# Python 3.14+ PEP 649支持
if sys.version_info >= (3, 14):
    import annotationlib

    # 全局Monkey-patch: 修复SQLModel在Python 3.14上的兼容性问题
    import sqlmodel.main
    _original_get_sqlalchemy_type = sqlmodel.main.get_sqlalchemy_type

    def _patched_get_sqlalchemy_type(field):
        """
        修复SQLModel的get_sqlalchemy_type函数，处理Python 3.14的类型问题。

        问题：
        1. ForwardRef对象（来自Relationship字段）会导致issubclass错误
        2. typing._GenericAlias对象（如ClassVar[T]）也会导致同样问题
        3. list/dict等泛型类型在没有Field/Relationship时可能导致错误
        4. Mapped类型在Python 3.14下可能出现在annotation中
        5. Annotated类型可能包含sa_type metadata（如Array[T]）
        6. 自定义类型（如NumpyVector）有__sqlmodel_sa_type__属性
        7. Pydantic已处理的Annotated类型会将metadata存储在field.metadata中

        解决：
        - 优先检查field.metadata中的__get_pydantic_core_schema__（Pydantic已处理的情况）
        - 检测__sqlmodel_sa_type__属性（NumpyVector等）
        - 检测Relationship/ClassVar等返回None
        - 对于Annotated类型，尝试提取sa_type metadata
        - 其他情况调用原始函数
        """
        # 优先检查 field.metadata（Pydantic已处理Annotated类型的情况）
        # 当使用 Array[T] 或 Annotated[T, metadata] 时，Pydantic会将metadata存储在这里
        metadata = getattr(field, 'metadata', None)
        if metadata:
            # metadata是一个列表，包含所有Annotated的元数据项
            for metadata_item in metadata:
                # 检查metadata_item是否有__get_pydantic_core_schema__方法
                if hasattr(metadata_item, '__get_pydantic_core_schema__'):
                    try:
                        # 调用获取schema
                        schema = metadata_item.__get_pydantic_core_schema__(None, None)
                        # 检查schema的metadata中是否有sa_type
                        if isinstance(schema, dict) and 'metadata' in schema:
                            sa_type = schema['metadata'].get('sa_type')
                            if sa_type is not None:
                                return sa_type
                    except (TypeError, AttributeError, KeyError):
                        # Pydantic schema获取可能失败（类型不匹配、缺少属性等）
                        # 这是正常情况，继续检查下一个metadata项
                        pass

        annotation = getattr(field, 'annotation', None)
        if annotation is not None:
            # 优先检查 __sqlmodel_sa_type__ 属性
            # 这处理 NumpyVector[dims, dtype] 等自定义类型
            if hasattr(annotation, '__sqlmodel_sa_type__'):
                return annotation.__sqlmodel_sa_type__

            # 检查自定义类型（如JSON100K）的 __get_pydantic_core_schema__ 方法
            # 这些类型在schema的metadata中定义sa_type
            if hasattr(annotation, '__get_pydantic_core_schema__'):
                try:
                    # 调用获取schema（传None作为handler，因为我们只需要metadata）
                    schema = annotation.__get_pydantic_core_schema__(annotation, lambda x: None)
                    # 检查schema的metadata中是否有sa_type
                    if isinstance(schema, dict) and 'metadata' in schema:
                        sa_type = schema['metadata'].get('sa_type')
                        if sa_type is not None:
                            return sa_type
                except (TypeError, AttributeError, KeyError):
                    # Schema获取失败，继续其他检查
                    pass

            anno_type_name = type(annotation).__name__

            # ForwardRef: Relationship字段的annotation
            if anno_type_name == 'ForwardRef':
                return None

            # AnnotatedAlias: 检查是否有sa_type metadata（如Array[T]）
            if anno_type_name == 'AnnotatedAlias' or anno_type_name == '_AnnotatedAlias':
                from typing import get_origin, get_args
                import typing

                # 尝试提取Annotated的metadata
                if hasattr(typing, 'get_args'):
                    args = get_args(annotation)
                    # args[0]是实际类型，args[1:]是metadata
                    for metadata in args[1:]:
                        # 检查metadata是否有__get_pydantic_core_schema__方法
                        if hasattr(metadata, '__get_pydantic_core_schema__'):
                            try:
                                # 调用获取schema
                                schema = metadata.__get_pydantic_core_schema__(None, None)
                                # 检查schema中是否有sa_type
                                if isinstance(schema, dict) and 'metadata' in schema:
                                    sa_type = schema['metadata'].get('sa_type')
                                    if sa_type is not None:
                                        return sa_type
                            except (TypeError, AttributeError, KeyError):
                                # Annotated metadata的schema获取可能失败
                                # 这是正常的类型检查过程，继续检查下一个metadata
                                pass

            # _GenericAlias或GenericAlias: typing泛型类型
            if anno_type_name in ('_GenericAlias', 'GenericAlias'):
                from typing import get_origin
                import typing
                origin = get_origin(annotation)

                # ClassVar必须跳过
                if origin is typing.ClassVar:
                    return None

                # list/dict/tuple/set等内置泛型，如果字段没有明确的Field或Relationship，也跳过
                # 这通常意味着它是Relationship字段或类变量
                if origin in (list, dict, tuple, set):
                    # 检查field_info是否存在且有意义
                    # Relationship字段会有特殊的field_info
                    field_info = getattr(field, 'field_info', None)
                    if field_info is None:
                        return None

            # Mapped: SQLAlchemy 2.0的Mapped类型，SQLModel不应该处理
            # 这可能是从父类继承的字段或Python 3.14注解处理的副作用
            # 检查类型名称和annotation的字符串表示
            if 'Mapped' in anno_type_name or 'Mapped' in str(annotation):
                return None

            # 检查annotation是否是Mapped类或其实例
            try:
                from sqlalchemy.orm import Mapped as SAMapped
                # 检查origin（对于Mapped[T]这种泛型）
                from typing import get_origin
                if get_origin(annotation) is SAMapped:
                    return None
                # 检查类型本身
                if annotation is SAMapped or isinstance(annotation, type) and issubclass(annotation, SAMapped):
                    return None
            except (ImportError, TypeError):
                # 如果SQLAlchemy没有Mapped或检查失败，继续
                pass

        # 其他情况正常处理
        return _original_get_sqlalchemy_type(field)

    sqlmodel.main.get_sqlalchemy_type = _patched_get_sqlalchemy_type

    # 第二个Monkey-patch: 修复继承表类中InstrumentedAttribute作为默认值的问题
    # 在Python 3.14 + SQLModel组合下，当子类（如SMSBaoProvider）继承父类（如VerificationCodeProvider）时，
    # 父类的关系字段（如server_config）会在子类的model_fields中出现，
    # 但其default值错误地设置为InstrumentedAttribute对象，而不是None
    # 这导致实例化时尝试设置InstrumentedAttribute为字段值，触发SQLAlchemy内部错误
    import sqlmodel._compat as _compat
    from sqlalchemy.orm import attributes as _sa_attributes

    _original_sqlmodel_table_construct = _compat.sqlmodel_table_construct

    def _patched_sqlmodel_table_construct(self_instance, values):
        """
        修复sqlmodel_table_construct，跳过InstrumentedAttribute默认值

        问题：
        - 继承自polymorphic基类的表类（如FishAudioTTS, SMSBaoProvider）
        - 其model_fields中的继承字段default值为InstrumentedAttribute
        - 原函数尝试将InstrumentedAttribute设置为字段值
        - SQLAlchemy无法处理，抛出 '_sa_instance_state' 错误

        解决：
        - 只设置用户提供的值和非InstrumentedAttribute默认值
        - InstrumentedAttribute默认值跳过（让SQLAlchemy自己处理）
        """
        cls = type(self_instance)

        # 收集要设置的字段值
        fields_to_set = {}

        for name, field in cls.model_fields.items():
            # 如果用户提供了值，直接使用
            if name in values:
                fields_to_set[name] = values[name]
                continue

            # 否则检查默认值
            # 跳过InstrumentedAttribute默认值 - 这些是继承字段的错误默认值
            if isinstance(field.default, _sa_attributes.InstrumentedAttribute):
                continue

            # 使用正常的默认值
            if field.default is not Undefined:
                fields_to_set[name] = field.default
            elif field.default_factory is not None:
                fields_to_set[name] = field.get_default(call_default_factory=True)

        # 设置属性 - 只设置非InstrumentedAttribute值
        for key, value in fields_to_set.items():
            if not isinstance(value, _sa_attributes.InstrumentedAttribute):
                setattr(self_instance, key, value)

        # 设置Pydantic内部属性
        object.__setattr__(self_instance, '__pydantic_fields_set__', set(values.keys()))
        if not cls.__pydantic_root_model__:
            _extra = None
            if cls.model_config.get('extra') == 'allow':
                _extra = {}
                for k, v in values.items():
                    if k not in cls.model_fields:
                        _extra[k] = v
            object.__setattr__(self_instance, '__pydantic_extra__', _extra)

        if cls.__pydantic_post_init__:
            self_instance.model_post_init(None)
        elif not cls.__pydantic_root_model__:
            object.__setattr__(self_instance, '__pydantic_private__', None)

        # 设置关系
        for key in self_instance.__sqlmodel_relationships__:
            value = values.get(key, Undefined)
            if value is not Undefined:
                setattr(self_instance, key, value)

        return self_instance

    _compat.sqlmodel_table_construct = _patched_sqlmodel_table_construct
else:
    annotationlib = None


def _extract_sa_type_from_annotation(annotation: Any) -> Any | None:
    """
    从类型注解中提取SQLAlchemy类型。

    支持以下形式：
    1. NumpyVector[256, np.float32] - 直接使用类型（有__sqlmodel_sa_type__属性）
    2. Annotated[np.ndarray, NumpyVector[256, np.float32]] - Annotated包装
    3. 任何有__get_pydantic_core_schema__且返回metadata['sa_type']的类型

    Args:
        annotation: 字段的类型注解

    Returns:
        提取到的SQLAlchemy类型，如果没有则返回None
    """
    # 方法1：直接检查类型本身是否有__sqlmodel_sa_type__属性
    # 这涵盖了 NumpyVector[256, np.float32] 这种直接使用的情况
    if hasattr(annotation, '__sqlmodel_sa_type__'):
        return annotation.__sqlmodel_sa_type__

    # 方法2：检查是否为Annotated类型
    if get_origin(annotation) is typing.Annotated:
        # 获取元数据项（跳过第一个实际类型参数）
        args = get_args(annotation)
        if len(args) >= 2:
            metadata_items = args[1:]  # 第一个是实际类型，后面都是元数据

            # 遍历元数据，查找包含sa_type的项
            for item in metadata_items:
                # 检查元数据项是否有__sqlmodel_sa_type__属性
                if hasattr(item, '__sqlmodel_sa_type__'):
                    return item.__sqlmodel_sa_type__

                # 检查是否有__get_pydantic_core_schema__方法
                if hasattr(item, '__get_pydantic_core_schema__'):
                    try:
                        # 调用该方法获取core schema
                        schema = item.__get_pydantic_core_schema__(
                            annotation,
                            lambda x: None  # 虚拟handler
                        )
                        # 检查schema的metadata中是否有sa_type
                        if isinstance(schema, dict) and 'metadata' in schema:
                            sa_type = schema['metadata'].get('sa_type')
                            if sa_type is not None:
                                return sa_type
                    except (TypeError, AttributeError, KeyError, ValueError):
                        # Pydantic core schema获取可能失败：
                        # - TypeError: 参数不匹配
                        # - AttributeError: metadata不存在
                        # - KeyError: schema结构不符合预期
                        # - ValueError: 无效的类型定义
                        # 这是正常的类型探测过程，继续检查下一个metadata项
                        pass

    # 方法3：检查类型本身是否有__get_pydantic_core_schema__
    # （虽然NumpyVector已经在方法1处理，但这是通用的fallback）
    if hasattr(annotation, '__get_pydantic_core_schema__'):
        try:
            schema = annotation.__get_pydantic_core_schema__(
                annotation,
                lambda x: None  # 虚拟handler
            )
            if isinstance(schema, dict) and 'metadata' in schema:
                sa_type = schema['metadata'].get('sa_type')
                if sa_type is not None:
                    return sa_type
        except (TypeError, AttributeError, KeyError, ValueError):
            # 类型本身的schema获取失败
            # 这是正常的fallback机制，annotation可能不支持此协议
            pass

    return None


def _resolve_annotations(attrs: dict[str, Any]) -> tuple[
    dict[str, Any],
    dict[str, str],
    Mapping[str, Any],
    Mapping[str, Any],
]:
    """
    Resolve annotations from a class namespace with Python 3.14 (PEP 649) support.

    This helper prefers evaluated annotations (Format.VALUE) so that `typing.Annotated`
    metadata and custom types remain accessible. Forward references that cannot be
    evaluated are replaced with typing.ForwardRef placeholders to avoid aborting the
    whole resolution process.
    """
    raw_annotations = attrs.get('__annotations__') or {}
    try:
        base_annotations = dict(raw_annotations)
    except TypeError:
        base_annotations = {}

    module_name = attrs.get('__module__')
    module_globals: dict[str, Any]
    if module_name and module_name in sys.modules:
        module_globals = dict(sys.modules[module_name].__dict__)
    else:
        module_globals = {}

    module_globals.setdefault('__builtins__', __builtins__)
    localns: dict[str, Any] = dict(attrs)

    try:
        temp_cls = type('AnnotationProxy', (object,), dict(attrs))
        temp_cls.__module__ = module_name
        extras_kw = {'include_extras': True} if sys.version_info >= (3, 10) else {}
        evaluated = get_type_hints(
            temp_cls,
            globalns=module_globals,
            localns=localns,
            **extras_kw,
        )
    except (NameError, AttributeError, TypeError, RecursionError):
        # get_type_hints可能失败的原因：
        # - NameError: 前向引用无法解析（类型尚未定义）
        # - AttributeError: 模块或类型不存在
        # - TypeError: 无效的类型注解
        # - RecursionError: 循环依赖的类型定义
        # 这是正常情况，回退到原始注解字符串
        evaluated = base_annotations

    return dict(evaluated), {}, module_globals, localns


def _evaluate_annotation_from_string(
    field_name: str,
    annotation_strings: dict[str, str],
    current_type: Any,
    globalns: Mapping[str, Any],
    localns: Mapping[str, Any],
) -> Any:
    """
    Attempt to re-evaluate the original annotation string for a field.

    This is used as a fallback when the resolved annotation lost its metadata
    (e.g., Annotated wrappers) and we need to recover custom sa_type data.
    """
    if not annotation_strings:
        return current_type

    expr = annotation_strings.get(field_name)
    if not expr or not isinstance(expr, str):
        return current_type

    try:
        return eval(expr, globalns, localns)
    except (NameError, SyntaxError, AttributeError, TypeError):
        # eval可能失败的原因：
        # - NameError: 类型名称在namespace中不存在
        # - SyntaxError: 注解字符串有语法错误
        # - AttributeError: 访问不存在的模块属性
        # - TypeError: 无效的类型表达式
        # 这是正常的fallback机制，返回当前已解析的类型
        return current_type


class __DeclarativeMeta(SQLModelMetaclass):
    """
    一个智能的混合模式元类，它提供了灵活性和清晰度：

    1.  **自动设置 `table=True`**: 如果一个类继承了 `TableBaseMixin`，则自动应用 `table=True`。
    2.  **明确的字典参数**: 支持 `mapper_args={...}`, `table_args={...}`, `table_name='...'`。
    3.  **便捷的关键字参数**: 支持最常见的 mapper 参数作为顶级关键字（如 `polymorphic_on`）。
    4.  **智能合并**: 当字典和关键字同时提供时，会自动合并，且关键字参数有更高优先级。
    """

    _KNOWN_MAPPER_KEYS = {
        "polymorphic_on",
        "polymorphic_identity",
        "polymorphic_abstract",
        "version_id_col",
        "concrete",
    }

    def __new__(cls, name, bases, attrs, **kwargs):
        # 1. 约定优于配置：自动设置 table=True
        is_intended_as_table = any(getattr(b, '_has_table_mixin', False) for b in bases)
        if is_intended_as_table and 'table' not in kwargs:
            kwargs['table'] = True

        # 2. 智能合并 __mapper_args__
        collected_mapper_args = {}

        # 首先，处理明确的 mapper_args 字典 (优先级较低)
        if 'mapper_args' in kwargs:
            collected_mapper_args.update(kwargs.pop('mapper_args'))

        # 其次，处理便捷的关键字参数 (优先级更高)
        for key in cls._KNOWN_MAPPER_KEYS:
            if key in kwargs:
                # .pop() 获取值并移除，避免传递给父类
                collected_mapper_args[key] = kwargs.pop(key)

        # 如果收集到了任何 mapper 参数，则更新到类的属性中
        if collected_mapper_args:
            existing = attrs.get('__mapper_args__', {}).copy()
            existing.update(collected_mapper_args)
            attrs['__mapper_args__'] = existing

        # 3. 处理其他明确的参数
        if 'table_args' in kwargs:
            attrs['__table_args__'] = kwargs.pop('table_args')
        if 'table_name' in kwargs:
            attrs['__tablename__'] = kwargs.pop('table_name')
        if 'abstract' in kwargs:
            attrs['__abstract__'] = kwargs.pop('abstract')

        # 4. 从Annotated元数据中提取sa_type并注入到Field
        # 重要：必须在调用父类__new__之前处理，因为SQLModel会消费annotations
        #
        # Python 3.14兼容性问题：
        # - SQLModel在Python 3.14上会因为ClassVar[T]类型而崩溃（issubclass错误）
        # - 我们必须在SQLModel看到annotations之前过滤掉ClassVar字段
        # - 虽然PEP 749建议不修改__annotations__，但这是修复SQLModel bug的必要措施
        #
        # 获取annotations的策略：
        # - Python 3.14+: 优先从__annotate__获取（如果存在）
        # - fallback: 从__annotations__读取（如果存在）
        # - 最终fallback: 空字典
        annotations, annotation_strings, eval_globals, eval_locals = _resolve_annotations(attrs)

        if annotations:
            attrs['__annotations__'] = annotations
            if annotationlib is not None:
                # 在Python 3.14中禁用descriptor，转为普通dict
                attrs['__annotate__'] = None

        for field_name, field_type in annotations.items():
            field_type = _evaluate_annotation_from_string(
                field_name,
                annotation_strings,
                field_type,
                eval_globals,
                eval_locals,
            )

            # 跳过字符串或ForwardRef类型注解，让SQLModel自己处理
            if isinstance(field_type, str) or isinstance(field_type, typing.ForwardRef):
                continue

            # 跳过特殊类型的字段
            origin = get_origin(field_type)

            # 跳过 ClassVar 字段 - 它们不是数据库字段
            if origin is typing.ClassVar:
                continue

            # 跳过 Mapped 字段 - SQLAlchemy 2.0+ 的声明式字段，已经有 mapped_column
            if origin is Mapped:
                continue

            # 尝试从注解中提取sa_type
            sa_type = _extract_sa_type_from_annotation(field_type)

            if sa_type is not None:
                # 检查字段是否已有Field定义
                field_value = attrs.get(field_name, Undefined)

                if field_value is Undefined:
                    # 没有Field定义，创建一个新的Field并注入sa_type
                    attrs[field_name] = Field(sa_type=sa_type)
                elif isinstance(field_value, FieldInfo):
                    # 已有Field定义，检查是否已设置sa_type
                    # 注意：只有在未设置时才注入，尊重显式配置
                    # SQLModel使用Undefined作为"未设置"的标记
                    if not hasattr(field_value, 'sa_type') or field_value.sa_type is Undefined:
                        field_value.sa_type = sa_type
                # 如果field_value是其他类型（如默认值），不处理
                # SQLModel会在后续处理中将其转换为Field

        # 5. 调用父类的 __new__ 方法，传入被清理过的 kwargs
        result = super().__new__(cls, name, bases, attrs, **kwargs)

        # 6. 修复：在联表继承场景下，继承父类的 __sqlmodel_relationships__
        # SQLModel 为每个 table=True 的类创建新的空 __sqlmodel_relationships__
        # 这导致子类丢失父类的关系定义，触发错误的 Column 创建
        # 必须在 super().__new__() 之后修复，因为 SQLModel 会覆盖我们预设的值
        if kwargs.get('table', False):
            for base in bases:
                if hasattr(base, '__sqlmodel_relationships__'):
                    for rel_name, rel_info in base.__sqlmodel_relationships__.items():
                        # 只继承子类没有重新定义的关系
                        if rel_name not in result.__sqlmodel_relationships__:
                            result.__sqlmodel_relationships__[rel_name] = rel_info
                            # 同时修复被错误创建的 Column - 恢复为父类的 relationship
                            if hasattr(base, rel_name):
                                base_attr = getattr(base, rel_name)
                                setattr(result, rel_name, base_attr)

        # 7. 检测：禁止子类重定义父类的 Relationship 字段
        # 子类重定义同名的 Relationship 字段会导致 SQLAlchemy 关系映射混乱，
        # 应该在类定义时立即报错，而不是在运行时出现难以调试的问题。
        for base in bases:
            parent_relationships = getattr(base, '__sqlmodel_relationships__', {})
            for rel_name in parent_relationships:
                # 检查当前类是否在 attrs 中重新定义了这个关系字段
                if rel_name in attrs:
                    raise TypeError(
                        f"类 {name} 不允许重定义父类 {base.__name__} 的 Relationship 字段 '{rel_name}'。"
                        f"如需修改关系配置，请在父类中修改。"
                    )

        # 8. 修复：从 model_fields/__pydantic_fields__ 中移除 Relationship 字段
        # SQLModel 0.0.27 bug：子类会错误地继承父类的 Relationship 字段到 model_fields
        # 这导致 Pydantic 尝试为 Relationship 字段生成 schema，因为类型是
        # Mapped[list['Character']] 这种前向引用，Pydantic 无法解析，
        # 导致 __pydantic_complete__ = False
        #
        # 修复策略：
        # - 检查类的 __sqlmodel_relationships__ 属性
        # - 从 model_fields 和 __pydantic_fields__ 中移除这些字段
        # - Relationship 字段由 SQLAlchemy 管理，不需要 Pydantic 参与
        relationships = getattr(result, '__sqlmodel_relationships__', {})
        if relationships:
            model_fields = getattr(result, 'model_fields', {})
            pydantic_fields = getattr(result, '__pydantic_fields__', {})

            fields_removed = False
            for rel_name in relationships:
                if rel_name in model_fields:
                    del model_fields[rel_name]
                    fields_removed = True
                if rel_name in pydantic_fields:
                    del pydantic_fields[rel_name]
                    fields_removed = True

            # 如果移除了字段，重新构建 Pydantic 模式
            # 注意：只在有字段被移除时才 rebuild，避免不必要的开销
            if fields_removed and hasattr(result, 'model_rebuild'):
                result.model_rebuild(force=True)

        return result

    def __init__(
        cls,
        classname: str,
        bases: tuple[type, ...],
        dict_: dict[str, typing.Any],
        **kw: typing.Any,
    ) -> None:
        """
        重写 SQLModel 的 __init__ 以支持联表继承（Joined Table Inheritance）

        SQLModel 原始行为：
        - 如果任何基类是表模型，则不调用 DeclarativeMeta.__init__
        - 这阻止了子类创建自己的表

        修复逻辑：
        - 检测联表继承场景（子类有自己的 __tablename__ 且有外键指向父表）
        - 强制调用 DeclarativeMeta.__init__ 来创建子表
        """
        from sqlmodel.main import is_table_model_class, DeclarativeMeta, ModelMetaclass

        # 检查是否是表模型
        if not is_table_model_class(cls):
            ModelMetaclass.__init__(cls, classname, bases, dict_, **kw)
            return

        # 检查是否有基类是表模型
        base_is_table = any(is_table_model_class(base) for base in bases)

        if not base_is_table:
            # 没有基类是表模型，走正常的 SQLModel 流程
            # 处理关系字段
            cls._setup_relationships()
            DeclarativeMeta.__init__(cls, classname, bases, dict_, **kw)
            return

        # 关键：检测联表继承场景
        # 条件：
        # 1. 当前类的 __tablename__ 与父类不同（表示需要新表）
        # 2. 当前类有字段带有 foreign_key 指向父表
        current_tablename = getattr(cls, '__tablename__', None)

        # 查找父表信息
        parent_table = None
        parent_tablename = None
        for base in bases:
            if is_table_model_class(base) and hasattr(base, '__tablename__'):
                parent_tablename = base.__tablename__
                break

        # 检查是否有不同的 tablename
        has_different_tablename = (
            current_tablename is not None
            and parent_tablename is not None
            and current_tablename != parent_tablename
        )

        # 检查是否有外键字段指向父表的主键
        # 注意：由于字段合并，我们需要检查直接基类的 model_fields
        # 而不是当前类的合并后的 model_fields
        has_fk_to_parent = False

        def _normalize_tablename(name: str) -> str:
            """标准化表名以进行比较（移除下划线，转小写）"""
            return name.replace('_', '').lower()

        def _fk_matches_parent(fk_str: str, parent_table: str) -> bool:
            """检查 FK 字符串是否指向父表"""
            if not fk_str or not parent_table:
                return False
            # FK 格式: "tablename.column" 或 "schema.tablename.column"
            parts = fk_str.split('.')
            if len(parts) >= 2:
                fk_table = parts[-2]  # 取倒数第二个作为表名
                # 标准化比较（处理下划线差异）
                return _normalize_tablename(fk_table) == _normalize_tablename(parent_table)
            return False

        if has_different_tablename and parent_tablename:
            # 首先检查当前类的 model_fields
            for field_name, field_info in cls.model_fields.items():
                fk = getattr(field_info, 'foreign_key', None)
                if fk is not None and isinstance(fk, str) and _fk_matches_parent(fk, parent_tablename):
                    has_fk_to_parent = True
                    break

            # 如果没找到，检查直接基类的 model_fields（解决 mixin 字段被覆盖的问题）
            if not has_fk_to_parent:
                for base in bases:
                    if hasattr(base, 'model_fields'):
                        for field_name, field_info in base.model_fields.items():
                            fk = getattr(field_info, 'foreign_key', None)
                            if fk is not None and isinstance(fk, str) and _fk_matches_parent(fk, parent_tablename):
                                has_fk_to_parent = True
                                break
                    if has_fk_to_parent:
                        break

        is_joined_inheritance = has_different_tablename and has_fk_to_parent

        if is_joined_inheritance:
            # 联表继承：需要创建子表

            # 修复外键字段：由于字段合并，外键信息可能丢失
            # 需要从基类的 mixin 中找回外键信息，并重建列
            from sqlalchemy import Column, ForeignKey, inspect as sa_inspect
            from sqlalchemy.dialects.postgresql import UUID as SA_UUID
            from sqlalchemy.exc import NoInspectionAvailable
            from sqlalchemy.orm.attributes import InstrumentedAttribute

            # 联表继承：子表只应该有 id（FK 到父表）+ 子类特有的字段
            # 所有继承自祖先表的列都不应该在子表中重复创建

            # 收集整个继承链中所有祖先表的列名（这些列不应该在子表中重复）
            # 需要遍历整个 MRO，因为可能是多级继承（如 Tool -> Function -> GetWeatherFunction）
            ancestor_column_names: set[str] = set()
            for ancestor in cls.__mro__:
                if ancestor is cls:
                    continue  # 跳过当前类
                if is_table_model_class(ancestor):
                    try:
                        # 使用 inspect() 获取 mapper 的公开属性
                        # 源码确认: mapper.local_table 是公开属性 (mapper.py:979-998)
                        mapper = sa_inspect(ancestor)
                        for col in mapper.local_table.columns:
                            # 跳过 _polymorphic_name 列（鉴别器，由根父表管理）
                            if col.name.startswith('_polymorphic'):
                                continue
                            ancestor_column_names.add(col.name)
                    except NoInspectionAvailable:
                        continue

            # 找到子类自己定义的字段（不在父类中的）
            child_own_fields: set[str] = set()
            for field_name in cls.model_fields:
                # 检查这个字段是否是在当前类直接定义的（不是继承的）
                # 通过检查父类是否有这个字段来判断
                is_inherited = False
                for base in bases:
                    if hasattr(base, 'model_fields') and field_name in base.model_fields:
                        is_inherited = True
                        break
                if not is_inherited:
                    child_own_fields.add(field_name)

            # 从子类类属性中移除父表已有的列定义
            # 这样 SQLAlchemy 就不会在子表中创建这些列
            fk_field_name = None
            for base in bases:
                if hasattr(base, 'model_fields'):
                    for field_name, field_info in base.model_fields.items():
                        fk = getattr(field_info, 'foreign_key', None)
                        pk = getattr(field_info, 'primary_key', False)
                        if fk is not None and isinstance(fk, str) and _fk_matches_parent(fk, parent_tablename):
                            fk_field_name = field_name
                            # 找到了外键字段，重建它
                            # 创建一个新的 Column 对象包含外键约束
                            new_col = Column(
                                field_name,
                                SA_UUID(as_uuid=True),
                                ForeignKey(fk),
                                primary_key=pk if pk else False
                            )
                            setattr(cls, field_name, new_col)
                            break
                    else:
                        continue
                    break

            # 移除继承自祖先表的列属性（除了 FK/PK 和子类自己的字段）
            # 这防止 SQLAlchemy 在子表中创建重复列
            # 注意：在 __init__ 阶段，列是 Column 对象，不是 InstrumentedAttribute
            for col_name in ancestor_column_names:
                if col_name == fk_field_name:
                    continue  # 保留 FK/PK 列（子表的主键，同时是父表的外键）
                if col_name == 'id':
                    continue  # id 会被 FK 字段覆盖
                if col_name in child_own_fields:
                    continue  # 保留子类自己定义的字段

                # 检查类属性是否是 Column 或 InstrumentedAttribute
                if col_name in cls.__dict__:
                    attr = cls.__dict__[col_name]
                    # Column 对象或 InstrumentedAttribute 都需要删除
                    if isinstance(attr, (Column, InstrumentedAttribute)):
                        try:
                            delattr(cls, col_name)
                        except AttributeError:
                            pass

            # 找到子类自己定义的关系（不在父类中的）
            # 继承的关系会从父类自动获取，只需要设置子类新增的关系
            child_own_relationships: set[str] = set()
            for rel_name in cls.__sqlmodel_relationships__:
                is_inherited = False
                for base in bases:
                    if hasattr(base, '__sqlmodel_relationships__') and rel_name in base.__sqlmodel_relationships__:
                        is_inherited = True
                        break
                if not is_inherited:
                    child_own_relationships.add(rel_name)

            # 只为子类自己定义的新关系调用关系设置
            if child_own_relationships:
                cls._setup_relationships(only_these=child_own_relationships)

            # 强制调用 DeclarativeMeta.__init__
            DeclarativeMeta.__init__(cls, classname, bases, dict_, **kw)
        else:
            # 非联表继承：单表继承或正常 Pydantic 模型
            ModelMetaclass.__init__(cls, classname, bases, dict_, **kw)

    def _setup_relationships(cls, only_these: set[str] | None = None) -> None:
        """
        设置 SQLAlchemy 关系字段（从 SQLModel 源码复制）

        Args:
            only_these: 如果提供，只设置这些关系（用于 joined table inheritance 子类）
                       如果为 None，设置所有关系（默认行为）
        """
        from sqlalchemy.orm import relationship, Mapped
        from sqlalchemy import inspect
        from sqlmodel.main import get_relationship_to
        from typing import get_origin

        for rel_name, rel_info in cls.__sqlmodel_relationships__.items():
            # 如果指定了 only_these，只设置这些关系
            if only_these is not None and rel_name not in only_these:
                continue
            if rel_info.sa_relationship:
                setattr(cls, rel_name, rel_info.sa_relationship)
                continue

            raw_ann = cls.__annotations__[rel_name]
            origin: typing.Any = get_origin(raw_ann)
            if origin is Mapped:
                ann = raw_ann.__args__[0]
            else:
                ann = raw_ann
                cls.__annotations__[rel_name] = Mapped[ann]

            relationship_to = get_relationship_to(
                name=rel_name, rel_info=rel_info, annotation=ann
            )
            rel_kwargs: dict[str, typing.Any] = {}
            if rel_info.back_populates:
                rel_kwargs["back_populates"] = rel_info.back_populates
            if rel_info.cascade_delete:
                rel_kwargs["cascade"] = "all, delete-orphan"
            if rel_info.passive_deletes:
                rel_kwargs["passive_deletes"] = rel_info.passive_deletes
            if rel_info.link_model:
                ins = inspect(rel_info.link_model)
                local_table = getattr(ins, "local_table")
                if local_table is None:
                    raise RuntimeError(
                        f"Couldn't find secondary table for {rel_info.link_model}"
                    )
                rel_kwargs["secondary"] = local_table

            rel_args: list[typing.Any] = []
            if rel_info.sa_relationship_args:
                rel_args.extend(rel_info.sa_relationship_args)
            if rel_info.sa_relationship_kwargs:
                rel_kwargs.update(rel_info.sa_relationship_kwargs)

            rel_value = relationship(relationship_to, *rel_args, **rel_kwargs)
            setattr(cls, rel_name, rel_value)


class SQLModelBase(SQLModel, metaclass=__DeclarativeMeta):
    """此类必须和TableBase系列类搭配使用"""

    model_config = ConfigDict(use_attribute_docstrings=True, validate_by_name=True)
