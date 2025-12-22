# SQLModels Base Module

This module provides `SQLModelBase`, the root base class for all SQLModel models in this project. It includes a custom metaclass with automatic type injection and Python 3.14 compatibility.

**Note**: Table base classes (`TableBaseMixin`, `UUIDTableBaseMixin`) and polymorphic utilities have been migrated to the [`sqlmodels.mixin`](../mixin/README.md) module. See the mixin documentation for CRUD operations, polymorphic inheritance patterns, and pagination utilities.

## Table of Contents

- [Overview](#overview)
- [Migration Notice](#migration-notice)
- [Python 3.14 Compatibility](#python-314-compatibility)
- [Core Component](#core-component)
  - [SQLModelBase](#sqlmodelbase)
- [Metaclass Features](#metaclass-features)
  - [Automatic sa_type Injection](#automatic-sa_type-injection)
  - [Table Configuration](#table-configuration)
  - [Polymorphic Support](#polymorphic-support)
- [Custom Types Integration](#custom-types-integration)
- [Best Practices](#best-practices)
- [Troubleshooting](#troubleshooting)

## Overview

The `sqlmodels.base` module provides `SQLModelBase`, the foundational base class for all SQLModel models. It features:

- **Smart metaclass** that automatically extracts and injects SQLAlchemy types from type annotations
- **Python 3.14 compatibility** through comprehensive PEP 649/749 support
- **Flexible configuration** through class parameters and automatic docstring support
- **Type-safe annotations** with automatic validation

All models in this project should directly or indirectly inherit from `SQLModelBase`.

---

## Migration Notice

As of the recent refactoring, the following components have been moved:

| Component | Old Location | New Location |
|-----------|-------------|--------------|
| `TableBase` → `TableBaseMixin` | `sqlmodels.base` | `sqlmodels.mixin` |
| `UUIDTableBase` → `UUIDTableBaseMixin` | `sqlmodels.base` | `sqlmodels.mixin` |
| `PolymorphicBaseMixin` | `sqlmodels.base` | `sqlmodels.mixin` |
| `create_subclass_id_mixin()` | `sqlmodels.base` | `sqlmodels.mixin` |
| `AutoPolymorphicIdentityMixin` | `sqlmodels.base` | `sqlmodels.mixin` |
| `TableViewRequest` | `sqlmodels.base` | `sqlmodels.mixin` |
| `now()`, `now_date()` | `sqlmodels.base` | `sqlmodels.mixin` |

**Update your imports**:

```python
# ❌ Old (deprecated)
from sqlmodels.base import TableBase, UUIDTableBase

# ✅ New (correct)
from sqlmodels.mixin import TableBaseMixin, UUIDTableBaseMixin
```

For detailed documentation on table mixins, CRUD operations, and polymorphic patterns, see [`sqlmodels/mixin/README.md`](../mixin/README.md).

---

## Python 3.14 Compatibility

### Overview

This module provides full compatibility with **Python 3.14's PEP 649** (Deferred Evaluation of Annotations) and **PEP 749** (making it the default).

**Key Changes in Python 3.14**:
- Annotations are no longer evaluated at class definition time
- Type hints are stored as deferred code objects
- `__annotate__` function generates annotations on demand
- Forward references become `ForwardRef` objects

### Implementation Strategy

We use **`typing.get_type_hints()`** as the universal annotations resolver:

```python
def _resolve_annotations(attrs: dict[str, Any]) -> tuple[...]:
    # Create temporary proxy class
    temp_cls = type('AnnotationProxy', (object,), dict(attrs))

    # Use get_type_hints with include_extras=True
    evaluated = get_type_hints(
        temp_cls,
        globalns=module_globals,
        localns=localns,
        include_extras=True  # Preserve Annotated metadata
    )

    return dict(evaluated), {}, module_globals, localns
```

**Why `get_type_hints()`?**
- ✅ Works across Python 3.10-3.14+
- ✅ Handles PEP 649 automatically
- ✅ Preserves `Annotated` metadata (with `include_extras=True`)
- ✅ Resolves forward references
- ✅ Recommended by Python documentation

### SQLModel Compatibility Patch

**Problem**: SQLModel's `get_sqlalchemy_type()` doesn't recognize custom types with `__sqlmodel_sa_type__` attribute.

**Solution**: Global monkey-patch that checks for SQLAlchemy type before falling back to original logic:

```python
if sys.version_info >= (3, 14):
    def _patched_get_sqlalchemy_type(field):
        annotation = getattr(field, 'annotation', None)
        if annotation is not None:
            # Priority 1: Check __sqlmodel_sa_type__ attribute
            # Handles NumpyVector[dims, dtype] and similar custom types
            if hasattr(annotation, '__sqlmodel_sa_type__'):
                return annotation.__sqlmodel_sa_type__

            # Priority 2: Check Annotated metadata
            if get_origin(annotation) is Annotated:
                for metadata in get_args(annotation)[1:]:
                    if hasattr(metadata, '__sqlmodel_sa_type__'):
                        return metadata.__sqlmodel_sa_type__

            # ... handle ForwardRef, ClassVar, etc.

        return _original_get_sqlalchemy_type(field)
```

### Supported Patterns

#### Pattern 1: Direct Custom Type Usage
```python
from sqlmodels.sqlmodel_types.dialects.postgresql import NumpyVector
from sqlmodels.mixin import UUIDTableBaseMixin

class SpeakerInfo(UUIDTableBaseMixin, table=True):
    embedding: NumpyVector[256, np.float32]
    """Voice embedding - sa_type automatically extracted"""
```

#### Pattern 2: Annotated Wrapper
```python
from typing import Annotated
from sqlmodels.mixin import UUIDTableBaseMixin

EmbeddingVector = Annotated[np.ndarray, NumpyVector[256, np.float32]]

class SpeakerInfo(UUIDTableBaseMixin, table=True):
    embedding: EmbeddingVector
```

#### Pattern 3: Array Type
```python
from sqlmodels.sqlmodel_types.dialects.postgresql import Array
from sqlmodels.mixin import TableBaseMixin

class ServerConfig(TableBaseMixin, table=True):
    protocols: Array[ProtocolEnum]
    """Allowed protocols - sa_type from Array handler"""
```

### Migration from Python 3.13

**No code changes required!** The implementation is transparent:

- Uses `typing.get_type_hints()` which works in both Python 3.13 and 3.14
- Custom types already use `__sqlmodel_sa_type__` attribute
- Monkey-patch only activates for Python 3.14+

---

## Core Component

### SQLModelBase

`SQLModelBase` is the root base class for all SQLModel models. It uses a custom metaclass (`__DeclarativeMeta`) that provides advanced features beyond standard SQLModel capabilities.

**Key Features**:
- Automatic `use_attribute_docstrings` configuration (use docstrings instead of `Field(description=...)`)
- Automatic `validate_by_name` configuration
- Custom metaclass for sa_type injection and polymorphic setup
- Integration with Pydantic v2
- Python 3.14 PEP 649 compatibility

**Usage**:

```python
from sqlmodels.base import SQLModelBase

class UserBase(SQLModelBase):
    name: str
    """User's display name"""

    email: str
    """User's email address"""
```

**Important Notes**:
- Use **docstrings** for field descriptions, not `Field(description=...)`
- Do NOT override `model_config` in subclasses (it's already configured in SQLModelBase)
- This class should be used for non-table models (DTOs, request/response models)

**For table models**, use mixins from `sqlmodels.mixin`:
- `TableBaseMixin` - Integer primary key with timestamps
- `UUIDTableBaseMixin` - UUID primary key with timestamps

See [`sqlmodels/mixin/README.md`](../mixin/README.md) for complete table mixin documentation.

---

## Metaclass Features

### Automatic sa_type Injection

The metaclass automatically extracts SQLAlchemy types from custom type annotations, enabling clean syntax for complex database types.

**Before** (verbose):
```python
from sqlmodels.sqlmodel_types.dialects.postgresql.numpy_vector import _NumpyVectorSQLAlchemyType
from sqlmodels.mixin import UUIDTableBaseMixin

class SpeakerInfo(UUIDTableBaseMixin, table=True):
    embedding: np.ndarray = Field(
        sa_type=_NumpyVectorSQLAlchemyType(256, np.float32)
    )
```

**After** (clean):
```python
from sqlmodels.sqlmodel_types.dialects.postgresql import NumpyVector
from sqlmodels.mixin import UUIDTableBaseMixin

class SpeakerInfo(UUIDTableBaseMixin, table=True):
    embedding: NumpyVector[256, np.float32]
    """Speaker voice embedding"""
```

**How It Works**:

The metaclass uses a three-tier detection strategy:

1. **Direct `__sqlmodel_sa_type__` attribute** (Priority 1)
   ```python
   if hasattr(annotation, '__sqlmodel_sa_type__'):
       return annotation.__sqlmodel_sa_type__
   ```

2. **Annotated metadata** (Priority 2)
   ```python
   # For Annotated[np.ndarray, NumpyVector[256, np.float32]]
   if get_origin(annotation) is typing.Annotated:
       for item in metadata_items:
           if hasattr(item, '__sqlmodel_sa_type__'):
               return item.__sqlmodel_sa_type__
   ```

3. **Pydantic Core Schema metadata** (Priority 3)
   ```python
   schema = annotation.__get_pydantic_core_schema__(...)
   if schema['metadata'].get('sa_type'):
       return schema['metadata']['sa_type']
   ```

After extracting `sa_type`, the metaclass:
- Creates `Field(sa_type=sa_type)` if no Field is defined
- Injects `sa_type` into existing Field if not already set
- Respects explicit `Field(sa_type=...)` (no override)

**Supported Patterns**:

```python
from sqlmodels.mixin import UUIDTableBaseMixin

# Pattern 1: Direct usage (recommended)
class Model(UUIDTableBaseMixin, table=True):
    embedding: NumpyVector[256, np.float32]

# Pattern 2: With Field constraints
class Model(UUIDTableBaseMixin, table=True):
    embedding: NumpyVector[256, np.float32] = Field(nullable=False)

# Pattern 3: Annotated wrapper
EmbeddingVector = Annotated[np.ndarray, NumpyVector[256, np.float32]]

class Model(UUIDTableBaseMixin, table=True):
    embedding: EmbeddingVector

# Pattern 4: Explicit sa_type (override)
class Model(UUIDTableBaseMixin, table=True):
    embedding: NumpyVector[256, np.float32] = Field(
        sa_type=_NumpyVectorSQLAlchemyType(128, np.float16)
    )
```

### Table Configuration

The metaclass provides smart defaults and flexible configuration:

**Automatic `table=True`**:
```python
# Classes inheriting from TableBaseMixin automatically get table=True
from sqlmodels.mixin import UUIDTableBaseMixin

class MyModel(UUIDTableBaseMixin):  # table=True is automatic
    pass
```

**Convenient mapper arguments**:
```python
# Instead of verbose __mapper_args__
from sqlmodels.mixin import UUIDTableBaseMixin

class MyModel(
    UUIDTableBaseMixin,
    polymorphic_on='_polymorphic_name',
    polymorphic_abstract=True
):
    pass

# Equivalent to:
class MyModel(UUIDTableBaseMixin):
    __mapper_args__ = {
        'polymorphic_on': '_polymorphic_name',
        'polymorphic_abstract': True
    }
```

**Smart merging**:
```python
# Dictionary and keyword arguments are merged
from sqlmodels.mixin import UUIDTableBaseMixin

class MyModel(
    UUIDTableBaseMixin,
    mapper_args={'version_id_col': 'version'},
    polymorphic_on='type'  # Merged into __mapper_args__
):
    pass
```

### Polymorphic Support

The metaclass supports SQLAlchemy's joined table inheritance through convenient parameters:

**Supported parameters**:
- `polymorphic_on`: Discriminator column name
- `polymorphic_identity`: Identity value for this class
- `polymorphic_abstract`: Whether this is an abstract base
- `table_args`: SQLAlchemy table arguments
- `table_name`: Override table name (becomes `__tablename__`)

**For complete polymorphic inheritance patterns**, including `PolymorphicBaseMixin`, `create_subclass_id_mixin()`, and `AutoPolymorphicIdentityMixin`, see [`sqlmodels/mixin/README.md`](../mixin/README.md).

---

## Custom Types Integration

### Using NumpyVector

The `NumpyVector` type demonstrates automatic sa_type injection:

```python
from sqlmodels.sqlmodel_types.dialects.postgresql import NumpyVector
from sqlmodels.mixin import UUIDTableBaseMixin
import numpy as np

class SpeakerInfo(UUIDTableBaseMixin, table=True):
    embedding: NumpyVector[256, np.float32]
    """Speaker voice embedding - sa_type automatically injected"""
```

**How NumpyVector works**:

```python
# NumpyVector[dims, dtype] returns a class with:
class _NumpyVectorType:
    __sqlmodel_sa_type__ = _NumpyVectorSQLAlchemyType(dimensions, dtype)

    @classmethod
    def __get_pydantic_core_schema__(cls, source_type, handler):
        return handler.generate_schema(np.ndarray)
```

This dual approach ensures:
1. Metaclass can extract `sa_type` via `__sqlmodel_sa_type__`
2. Pydantic can validate as `np.ndarray`

### Creating Custom SQLAlchemy Types

To create types that work with automatic injection, provide one of:

**Option 1: `__sqlmodel_sa_type__` attribute** (preferred):

```python
from sqlalchemy import TypeDecorator, String

class UpperCaseString(TypeDecorator):
    impl = String

    def process_bind_param(self, value, dialect):
        return value.upper() if value else value

class UpperCaseType:
    __sqlmodel_sa_type__ = UpperCaseString()

    @classmethod
    def __get_pydantic_core_schema__(cls, source_type, handler):
        return core_schema.str_schema()

# Usage
from sqlmodels.mixin import UUIDTableBaseMixin

class MyModel(UUIDTableBaseMixin, table=True):
    code: UpperCaseType  # Automatically uses UpperCaseString()
```

**Option 2: Pydantic metadata with sa_type**:

```python
def __get_pydantic_core_schema__(self, source_type, handler):
    return core_schema.json_or_python_schema(
        json_schema=core_schema.str_schema(),
        python_schema=core_schema.str_schema(),
        metadata={'sa_type': UpperCaseString()}
    )
```

**Option 3: Using Annotated**:

```python
from typing import Annotated
from sqlmodels.mixin import UUIDTableBaseMixin

UpperCase = Annotated[str, UpperCaseType()]

class MyModel(UUIDTableBaseMixin, table=True):
    code: UpperCase
```

---

## Best Practices

### 1. Inherit from correct base classes

```python
from sqlmodels.base import SQLModelBase
from sqlmodels.mixin import TableBaseMixin, UUIDTableBaseMixin

# ✅ For non-table models (DTOs, requests, responses)
class UserBase(SQLModelBase):
    name: str

# ✅ For table models with UUID primary key
class User(UserBase, UUIDTableBaseMixin, table=True):
    email: str

# ✅ For table models with custom primary key
class LegacyUser(TableBaseMixin, table=True):
    id: int = Field(primary_key=True)
    username: str
```

### 2. Use docstrings for field descriptions

```python
from sqlmodels.mixin import UUIDTableBaseMixin

# ✅ Recommended
class User(UUIDTableBaseMixin, table=True):
    name: str
    """User's display name"""

# ❌ Avoid
class User(UUIDTableBaseMixin, table=True):
    name: str = Field(description="User's display name")
```

**Why?** SQLModelBase has `use_attribute_docstrings=True`, so docstrings automatically become field descriptions in API docs.

### 3. Leverage automatic sa_type injection

```python
from sqlmodels.mixin import UUIDTableBaseMixin

# ✅ Clean and recommended
class SpeakerInfo(UUIDTableBaseMixin, table=True):
    embedding: NumpyVector[256, np.float32]
    """Voice embedding"""

# ❌ Verbose and unnecessary
class SpeakerInfo(UUIDTableBaseMixin, table=True):
    embedding: np.ndarray = Field(
        sa_type=_NumpyVectorSQLAlchemyType(256, np.float32)
    )
```

### 4. Follow polymorphic naming conventions

See [`sqlmodels/mixin/README.md`](../mixin/README.md) for complete polymorphic inheritance patterns using `PolymorphicBaseMixin`, `create_subclass_id_mixin()`, and `AutoPolymorphicIdentityMixin`.

### 5. Separate Base, Parent, and Implementation classes

```python
from abc import ABC, abstractmethod
from sqlmodels.base import SQLModelBase
from sqlmodels.mixin import UUIDTableBaseMixin, PolymorphicBaseMixin

# ✅ Recommended structure
class ASRBase(SQLModelBase):
    """Pure data fields, no table"""
    name: str
    base_url: str

class ASR(ASRBase, UUIDTableBaseMixin, PolymorphicBaseMixin, ABC):
    """Abstract parent with table"""
    @abstractmethod
    async def transcribe(self, audio: bytes) -> str:
        pass

class WhisperASR(ASR, table=True):
    """Concrete implementation"""
    model_size: str

    async def transcribe(self, audio: bytes) -> str:
        # Implementation
        pass
```

**Why?**
- Base class can be reused for DTOs
- Parent class defines the polymorphic hierarchy
- Implementation classes are clean and focused

---

## Troubleshooting

### Issue: ValueError: X has no matching SQLAlchemy type

**Solution**: Ensure your custom type provides `__sqlmodel_sa_type__` attribute or proper Pydantic metadata with `sa_type`.

```python
# ✅ Provide __sqlmodel_sa_type__
class MyType:
    __sqlmodel_sa_type__ = MyCustomSQLAlchemyType()
```

### Issue: Can't generate DDL for NullType()

**Symptoms**: Error during table creation saying a column has `NullType`.

**Root Cause**: Custom type's `sa_type` not detected by SQLModel.

**Solution**:
1. Ensure your type has `__sqlmodel_sa_type__` class attribute
2. Check that the monkey-patch is active (`sys.version_info >= (3, 14)`)
3. Verify type annotation is correct (not a string forward reference)

```python
from sqlmodels.mixin import UUIDTableBaseMixin

# ✅ Correct
class Model(UUIDTableBaseMixin, table=True):
    data: NumpyVector[256, np.float32]  # __sqlmodel_sa_type__ detected

# ❌ Wrong (string annotation)
class Model(UUIDTableBaseMixin, table=True):
    data: 'NumpyVector[256, np.float32]'  # sa_type lost
```

### Issue: Polymorphic identity conflicts

**Symptoms**: SQLAlchemy raises errors about duplicate polymorphic identities.

**Solution**:
1. Check that each concrete class has a unique identity
2. Use `AutoPolymorphicIdentityMixin` for automatic naming
3. Manually specify identity if needed:
   ```python
   class MyClass(Parent, polymorphic_identity='unique.name', table=True):
       pass
   ```

### Issue: Python 3.14 annotation errors

**Symptoms**: Errors related to `__annotations__` or type resolution.

**Solution**: The implementation uses `get_type_hints()` which handles PEP 649 automatically. If issues persist:
1. Check for manual `__annotations__` manipulation (avoid it)
2. Ensure all types are properly imported
3. Avoid `from __future__ import annotations` (can cause SQLModel issues)

### Issue: Polymorphic and CRUD-related errors

For issues related to polymorphic inheritance, CRUD operations, or table mixins, see the troubleshooting section in [`sqlmodels/mixin/README.md`](../mixin/README.md).

---

## Implementation Details

For developers modifying this module:

**Core files**:
- `sqlmodel_base.py` - Contains `__DeclarativeMeta` and `SQLModelBase`
- `../mixin/table.py` - Contains `TableBaseMixin` and `UUIDTableBaseMixin`
- `../mixin/polymorphic.py` - Contains `PolymorphicBaseMixin`, `create_subclass_id_mixin()`, and `AutoPolymorphicIdentityMixin`

**Key functions in this module**:

1. **`_resolve_annotations(attrs: dict[str, Any])`**
   - Uses `typing.get_type_hints()` for Python 3.14 compatibility
   - Returns tuple: `(annotations, annotation_strings, globalns, localns)`
   - Preserves `Annotated` metadata with `include_extras=True`

2. **`_extract_sa_type_from_annotation(annotation: Any) -> Any | None`**
   - Extracts SQLAlchemy type from type annotations
   - Supports `__sqlmodel_sa_type__`, `Annotated`, and Pydantic core schema
   - Called by metaclass during class creation

3. **`_patched_get_sqlalchemy_type(field)`** (Python 3.14+)
   - Global monkey-patch for SQLModel
   - Checks `__sqlmodel_sa_type__` before falling back to original logic
   - Handles custom types like `NumpyVector` and `Array`

4. **`__DeclarativeMeta.__new__()`**
   - Processes class definition parameters
   - Injects `sa_type` into field definitions
   - Sets up `__mapper_args__`, `__table_args__`, etc.
   - Handles Python 3.14 annotations via `get_type_hints()`

**Metaclass processing order**:
1. Check if class should be a table (`_is_table_mixin`)
2. Collect `__mapper_args__` from kwargs and explicit dict
3. Process `table_args`, `table_name`, `abstract` parameters
4. Resolve annotations using `get_type_hints()`
5. For each field, try to extract `sa_type` and inject into Field
6. Call parent metaclass with cleaned kwargs

For table mixin implementation details, see [`sqlmodels/mixin/README.md`](../mixin/README.md).

---

## See Also

**Project Documentation**:
- [SQLModel Mixin Documentation](../mixin/README.md) - Table mixins, CRUD operations, polymorphic patterns
- [Project Coding Standards (CLAUDE.md)](/mnt/c/Users/Administrator/PycharmProjects/emoecho-backend-server/CLAUDE.md)
- [Custom SQLModel Types Guide](/mnt/c/Users/Administrator/PycharmProjects/emoecho-backend-server/sqlmodels/sqlmodel_types/README.md)

**External References**:
- [SQLAlchemy Joined Table Inheritance](https://docs.sqlalchemy.org/en/20/orm/inheritance.html#joined-table-inheritance)
- [Pydantic V2 Documentation](https://docs.pydantic.dev/latest/)
- [SQLModel Documentation](https://sqlmodel.tiangolo.com/)
- [PEP 649: Deferred Evaluation of Annotations](https://peps.python.org/pep-0649/)
- [PEP 749: Implementing PEP 649](https://peps.python.org/pep-0749/)
- [Python Annotations Best Practices](https://docs.python.org/3/howto/annotations.html)
