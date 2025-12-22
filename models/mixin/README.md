# SQLModel Mixin Module

This module provides composable Mixin classes for SQLModel entities, enabling reusable functionality such as CRUD operations, polymorphic inheritance, JWT authentication, and standardized response DTOs.

## Module Overview

The `sqlmodels.mixin` module contains various Mixin classes that follow the "Composition over Inheritance" design philosophy. These mixins provide:

- **CRUD Operations**: Async database operations (add, save, update, delete, get, count)
- **Polymorphic Inheritance**: Tools for joined table inheritance patterns
- **JWT Authentication**: Token generation and validation
- **Pagination & Sorting**: Standardized table view parameters
- **Response DTOs**: Consistent id/timestamp fields for API responses

## Module Structure

```
sqlmodels/mixin/
├── __init__.py          # Module exports
├── polymorphic.py       # PolymorphicBaseMixin, create_subclass_id_mixin, AutoPolymorphicIdentityMixin
├── table.py             # TableBaseMixin, UUIDTableBaseMixin, TableViewRequest
├── info_response.py     # Response DTO Mixins (IntIdInfoMixin, UUIDIdInfoMixin, etc.)
└── jwt/                 # JWT authentication
    ├── __init__.py
    ├── key.py           # JWTKey database model
    ├── payload.py       # JWTPayloadBase
    ├── manager.py       # JWTManager singleton
    ├── auth.py          # JWTAuthMixin
    ├── exceptions.py    # JWT-related exceptions
    └── responses.py     # TokenResponse DTO
```

## Dependency Hierarchy

The module has a strict import order to avoid circular dependencies:

1. **polymorphic.py** - Only depends on `SQLModelBase`
2. **table.py** - Depends on `polymorphic.py`
3. **jwt/** - May depend on both `polymorphic.py` and `table.py`
4. **info_response.py** - Only depends on `SQLModelBase`

## Core Components

### 1. TableBaseMixin

Base mixin for database table models with integer primary keys.

**Features:**
- Provides CRUD methods: `add()`, `save()`, `update()`, `delete()`, `get()`, `count()`, `get_exist_one()`
- Automatic timestamp management (`created_at`, `updated_at`)
- Async relationship loading support (via `AsyncAttrs`)
- Pagination and sorting via `TableViewRequest`
- Polymorphic subclass loading support

**Fields:**
- `id: int | None` - Integer primary key (auto-increment)
- `created_at: datetime` - Record creation timestamp
- `updated_at: datetime` - Record update timestamp (auto-updated)

**Usage:**
```python
from sqlmodels.mixin import TableBaseMixin
from sqlmodels.base import SQLModelBase

class User(SQLModelBase, TableBaseMixin, table=True):
    name: str
    email: str
    """User email"""

# CRUD operations
async def example(session: AsyncSession):
    # Add
    user = User(name="Alice", email="alice@example.com")
    user = await user.save(session)

    # Get
    user = await User.get(session, User.id == 1)

    # Update
    update_data = UserUpdateRequest(name="Alice Smith")
    user = await user.update(session, update_data)

    # Delete
    await User.delete(session, user)

    # Count
    count = await User.count(session, User.is_active == True)
```

**Important Notes:**
- `save()` and `update()` return refreshed instances - **always use the return value**:
  ```python
  # ✅ Correct
  device = await device.save(session)
  return device

  # ❌ Wrong - device is expired after commit
  await device.save(session)
  return device
  ```

### 2. UUIDTableBaseMixin

Extends `TableBaseMixin` with UUID primary keys instead of integers.

**Differences from TableBaseMixin:**
- `id: UUID` - UUID primary key (auto-generated via `uuid.uuid4()`)
- `get_exist_one()` accepts `UUID` instead of `int`

**Usage:**
```python
from sqlmodels.mixin import UUIDTableBaseMixin

class Character(SQLModelBase, UUIDTableBaseMixin, table=True):
    name: str
    description: str | None = None
    """Character description"""
```

**Recommendation:** Use `UUIDTableBaseMixin` for most new models, as UUIDs provide better scalability and avoid ID collisions.

### 3. TableViewRequest

Standardized pagination and sorting parameters for LIST endpoints.

**Fields:**
- `offset: int | None` - Skip first N records (default: 0)
- `limit: int | None` - Return max N records (default: 50, max: 100)
- `desc: bool | None` - Sort descending (default: True)
- `order: Literal["created_at", "updated_at"] | None` - Sort field (default: "created_at")

**Usage with TableBaseMixin.get():**
```python
from dependencies import TableViewRequestDep

@router.get("/list")
async def list_characters(
    session: SessionDep,
    table_view: TableViewRequestDep
) -> list[Character]:
    """List characters with pagination and sorting"""
    return await Character.get(
        session,
        fetch_mode="all",
        table_view=table_view  # Automatically handles pagination and sorting
    )
```

**Manual usage:**
```python
table_view = TableViewRequest(offset=0, limit=20, desc=True, order="created_at")
characters = await Character.get(session, fetch_mode="all", table_view=table_view)
```

**Backward Compatibility:**
The traditional `offset`, `limit`, `order_by` parameters still work, but `table_view` is recommended for new code.

### 4. PolymorphicBaseMixin

Base mixin for joined table inheritance, automatically configuring polymorphic settings.

**Automatic Configuration:**
- Defines `_polymorphic_name: str` field (indexed)
- Sets `polymorphic_on='_polymorphic_name'`
- Detects abstract classes (via ABC and abstract methods) and sets `polymorphic_abstract=True`

**Methods:**
- `get_concrete_subclasses()` - Get all non-abstract subclasses (for `selectin_polymorphic`)
- `get_polymorphic_discriminator()` - Get the polymorphic discriminator field name
- `get_identity_to_class_map()` - Map `polymorphic_identity` to subclass types

**Usage:**
```python
from abc import ABC, abstractmethod
from sqlmodels.mixin import PolymorphicBaseMixin, UUIDTableBaseMixin

class Tool(PolymorphicBaseMixin, UUIDTableBaseMixin, ABC):
    """Abstract base class for all tools"""
    name: str
    description: str
    """Tool description"""

    @abstractmethod
    async def execute(self, params: dict) -> dict:
        """Execute the tool"""
        pass
```

**Why Single Underscore Prefix?**
- SQLAlchemy maps single-underscore fields to database columns
- Pydantic treats them as private (excluded from serialization)
- Double-underscore fields would be excluded by SQLAlchemy (not mapped to database)

### 5. create_subclass_id_mixin()

Factory function to create ID mixins for subclasses in joined table inheritance.

**Purpose:** In joined table inheritance, subclasses need a foreign key pointing to the parent table's primary key. This function generates a mixin class providing that foreign key field.

**Signature:**
```python
def create_subclass_id_mixin(parent_table_name: str) -> type[SQLModelBase]:
    """
    Args:
        parent_table_name: Parent table name (e.g., 'asr', 'tts', 'tool', 'function')

    Returns:
        A mixin class containing id field (foreign key + primary key)
    """
```

**Usage:**
```python
from sqlmodels.mixin import create_subclass_id_mixin

# Create mixin for ASR subclasses
ASRSubclassIdMixin = create_subclass_id_mixin('asr')

class FunASR(ASRSubclassIdMixin, ASR, AutoPolymorphicIdentityMixin, table=True):
    """FunASR implementation"""
    pass
```

**Important:** The ID mixin **must be first in the inheritance list** to ensure MRO (Method Resolution Order) correctly overrides the parent's `id` field.

### 6. AutoPolymorphicIdentityMixin

Automatically generates `polymorphic_identity` based on class name.

**Naming Convention:**
- Format: `{parent_identity}.{classname_lowercase}`
- If no parent identity exists, uses `{classname_lowercase}`

**Usage:**
```python
from sqlmodels.mixin import AutoPolymorphicIdentityMixin

class Function(Tool, AutoPolymorphicIdentityMixin, polymorphic_abstract=True):
    """Base class for function-type tools"""
    pass
    # polymorphic_identity = 'function'

class GetWeatherFunction(Function, table=True):
    """Weather query function"""
    pass
    # polymorphic_identity = 'function.getweatherfunction'
```

**Manual Override:**
```python
class CustomTool(
    Tool,
    AutoPolymorphicIdentityMixin,
    polymorphic_identity='custom_name',  # Override auto-generated name
    table=True
):
    pass
```

### 7. JWTAuthMixin

Provides JWT token generation and validation for entity classes (User, Client).

**Methods:**
- `async issue_jwt(session: AsyncSession) -> str` - Generate JWT token for current instance
- `@classmethod async from_jwt(session: AsyncSession, token: str) -> Self` - Validate token and retrieve entity

**Requirements:**
Subclasses must define:
- `JWTPayload` - Payload model (inherits from `JWTPayloadBase`)
- `jwt_key_purpose` - ClassVar specifying the JWT key purpose enum value

**Usage:**
```python
from sqlmodels.mixin import JWTAuthMixin, UUIDTableBaseMixin

class User(SQLModelBase, UUIDTableBaseMixin, JWTAuthMixin, table=True):
    JWTPayload = UserJWTPayload  # Define payload model
    jwt_key_purpose: ClassVar[JWTKeyPurposeEnum] = JWTKeyPurposeEnum.user

    email: str
    is_admin: bool = False
    is_active: bool = True
    """User active status"""

# Generate token
async def login(session: AsyncSession, user: User) -> str:
    token = await user.issue_jwt(session)
    return token

# Validate token
async def verify(session: AsyncSession, token: str) -> User:
    user = await User.from_jwt(session, token)
    return user
```

### 8. Response DTO Mixins

Mixins for standardized InfoResponse DTOs, defining id and timestamp fields.

**Available Mixins:**
- `IntIdInfoMixin` - Integer ID field
- `UUIDIdInfoMixin` - UUID ID field
- `DatetimeInfoMixin` - `created_at` and `updated_at` fields
- `IntIdDatetimeInfoMixin` - Integer ID + timestamps
- `UUIDIdDatetimeInfoMixin` - UUID ID + timestamps

**Design Note:** These fields are non-nullable in DTOs because database records always have these values when returned.

**Usage:**
```python
from sqlmodels.mixin import UUIDIdDatetimeInfoMixin

class CharacterInfoResponse(CharacterBase, UUIDIdDatetimeInfoMixin):
    """Character response DTO with id and timestamps"""
    pass  # Inherits id, created_at, updated_at from mixin
```

## Complete Joined Table Inheritance Example

Here's a complete example demonstrating polymorphic inheritance:

```python
from abc import ABC, abstractmethod
from sqlmodels.base import SQLModelBase
from sqlmodels.mixin import (
    UUIDTableBaseMixin,
    PolymorphicBaseMixin,
    create_subclass_id_mixin,
    AutoPolymorphicIdentityMixin,
)

# 1. Define Base class (fields only, no table)
class ASRBase(SQLModelBase):
    name: str
    """Configuration name"""

    base_url: str
    """Service URL"""

# 2. Define abstract parent class (with table)
class ASR(ASRBase, UUIDTableBaseMixin, PolymorphicBaseMixin, ABC):
    """Abstract base class for ASR configurations"""
    # PolymorphicBaseMixin automatically provides:
    # - _polymorphic_name field
    # - polymorphic_on='_polymorphic_name'
    # - polymorphic_abstract=True (when ABC with abstract methods)

    @abstractmethod
    async def transcribe(self, pcm_data: bytes) -> str:
        """Transcribe audio to text"""
        pass

# 3. Create ID Mixin for second-level subclasses
ASRSubclassIdMixin = create_subclass_id_mixin('asr')

# 4. Create second-level abstract class (if needed)
class FunASR(
    ASRSubclassIdMixin,
    ASR,
    AutoPolymorphicIdentityMixin,
    polymorphic_abstract=True
):
    """FunASR abstract base (may have multiple implementations)"""
    pass
    # polymorphic_identity = 'funasr'

# 5. Create concrete implementation classes
class FunASRLocal(FunASR, table=True):
    """FunASR local deployment"""
    # polymorphic_identity = 'funasr.funasrlocal'

    async def transcribe(self, pcm_data: bytes) -> str:
        # Implementation...
        return "transcribed text"

# 6. Get all concrete subclasses (for selectin_polymorphic)
concrete_asrs = ASR.get_concrete_subclasses()
# Returns: [FunASRLocal, ...]
```

## Import Guidelines

**Standard Import:**
```python
from sqlmodels.mixin import (
    TableBaseMixin,
    UUIDTableBaseMixin,
    PolymorphicBaseMixin,
    TableViewRequest,
    create_subclass_id_mixin,
    AutoPolymorphicIdentityMixin,
    JWTAuthMixin,
    UUIDIdDatetimeInfoMixin,
    now,
    now_date,
)
```

**Backward Compatibility:**
Some exports are also available from `sqlmodels.base` for backward compatibility:
```python
# Legacy import path (still works)
from sqlmodels.base import UUIDTableBase, TableViewRequest

# Recommended new import path
from sqlmodels.mixin import UUIDTableBaseMixin, TableViewRequest
```

## Best Practices

### 1. Mixin Order Matters

**Correct Order:**
```python
# ✅ ID Mixin first, then parent, then AutoPolymorphicIdentityMixin
class SubTool(ToolSubclassIdMixin, Tool, AutoPolymorphicIdentityMixin, table=True):
    pass
```

**Wrong Order:**
```python
# ❌ ID Mixin not first - won't override parent's id field
class SubTool(Tool, ToolSubclassIdMixin, AutoPolymorphicIdentityMixin, table=True):
    pass
```

### 2. Always Use Return Values from save() and update()

```python
# ✅ Correct - use returned instance
device = await device.save(session)
return device

# ❌ Wrong - device is expired after commit
await device.save(session)
return device  # AttributeError when accessing fields
```

### 3. Prefer table_view Over Manual Pagination

```python
# ✅ Recommended - consistent across all endpoints
characters = await Character.get(
    session,
    fetch_mode="all",
    table_view=table_view
)

# ⚠️ Works but not recommended - manual parameter management
characters = await Character.get(
    session,
    fetch_mode="all",
    offset=0,
    limit=20,
    order_by=[desc(Character.created_at)]
)
```

### 4. Polymorphic Loading for Many Subclasses

```python
# When loading relationships with > 10 polymorphic subclasses, use load_polymorphic='all'
tool_set = await ToolSet.get(
    session,
    ToolSet.id == tool_set_id,
    load=ToolSet.tools,
    load_polymorphic='all'  # Two-phase query - only loads actual related subclasses
)

# For fewer subclasses, specify the list explicitly
tool_set = await ToolSet.get(
    session,
    ToolSet.id == tool_set_id,
    load=ToolSet.tools,
    load_polymorphic=[GetWeatherFunction, CodeInterpreterFunction]
)
```

### 5. Response DTOs Should Inherit Base Classes

```python
# ✅ Correct - inherits from CharacterBase
class CharacterInfoResponse(CharacterBase, UUIDIdDatetimeInfoMixin):
    pass

# ❌ Wrong - doesn't inherit from CharacterBase
class CharacterInfoResponse(SQLModelBase, UUIDIdDatetimeInfoMixin):
    name: str  # Duplicated field definition
    description: str | None = None
```

**Reason:** Inheriting from Base classes ensures:
- Type checking via `isinstance(obj, XxxBase)`
- Consistency across related DTOs
- Future field additions automatically propagate

### 6. Use Specific Types, Not Containers

```python
# ✅ Correct - specific DTO for config updates
class GetWeatherFunctionUpdateRequest(GetWeatherFunctionConfigBase):
    weather_api_key: str | None = None
    default_location: str | None = None
    """Default location"""

# ❌ Wrong - lose type safety
class ToolUpdateRequest(SQLModelBase):
    config: dict[str, Any]  # No field validation
```

## Type Variables

```python
from sqlmodels.mixin import T, M

T = TypeVar("T", bound="TableBaseMixin")  # For CRUD methods
M = TypeVar("M", bound="SQLModel")        # For update() method
```

## Utility Functions

```python
from sqlmodels.mixin import now, now_date

# Lambda functions for default factories
now = lambda: datetime.now()
now_date = lambda: datetime.now().date()
```

## Related Modules

- **sqlmodels.base** - Base classes (`SQLModelBase`, backward-compatible exports)
- **dependencies** - FastAPI dependencies (`SessionDep`, `TableViewRequestDep`)
- **sqlmodels.user** - User model with JWT authentication
- **sqlmodels.client** - Client model with JWT authentication
- **sqlmodels.character.llm.openai_compatibles.tools** - Polymorphic tool hierarchy

## Additional Resources

- `POLYMORPHIC_NAME_DESIGN.md` - Design rationale for `_polymorphic_name` field
- `CLAUDE.md` - Project coding standards and design philosophy
- SQLAlchemy Documentation - [Joined Table Inheritance](https://docs.sqlalchemy.org/en/20/orm/inheritance.html#joined-table-inheritance)
