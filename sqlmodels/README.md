# Models 数据库模型文档

本目录包含 DiskNext Server 的所有数据库模型定义，基于 SQLModel 框架实现。

## 目录结构

```
models/
├── base/                   # 基础模型类
│   ├── __init__.py         # 导出 SQLModelBase
│   └── sqlmodel_base.py    # SQLModelBase 基类（自定义元类，支持联表继承）
├── mixin/                  # Mixin 模块
│   ├── __init__.py         # 统一导出
│   ├── table.py            # TableBaseMixin, UUIDTableBaseMixin（CRUD + 时间戳 + 分页）
│   ├── polymorphic.py      # 联表继承工具（create_subclass_id_mixin 等）
│   └── info_response.py    # DTO 用的 id/时间戳 Mixin
├── user.py                 # 用户模型
├── user_authn.py           # 用户 WebAuthn 凭证
├── group.py                # 用户组模型
├── policy.py               # 存储策略模型
├── physical_file.py        # 物理文件模型（文件去重）
├── object.py               # 统一对象模型（文件/目录）+ 上传会话 + 文件元数据
├── share.py                # 分享模型
├── tag.py                  # 标签模型
├── download.py             # 离线下载任务
├── task.py                 # 任务模型
├── node.py                 # 节点模型
├── order.py                # 订单模型
├── redeem.py               # 兑换码模型
├── report.py               # 举报模型
├── setting.py              # 系统设置模型
├── source_link.py          # 源链接模型
├── storage_pack.py         # 容量包模型
├── webdav.py               # WebDAV 账户模型
├── color.py                # 主题颜色 DTO
├── model_base.py           # 响应基类 DTO（ResponseBase, MCP 等）
├── migration.py            # 数据库初始化和迁移
└── database.py             # 数据库连接配置
```

---

## 基础类

### SQLModelBase

所有模型的基类，位于 `models.base.sqlmodel_base`，使用自定义元类 `__DeclarativeMeta` 实现：
- `use_attribute_docstrings=True`：使用属性后的 docstring 作为字段描述
- `validate_by_name=True`：允许按名称验证
- **自动设置 table=True**：继承 TableBaseMixin 的类自动成为数据库表
- **联表继承支持**：自动检测并处理 Joined Table Inheritance
- **多态支持**：支持 `polymorphic_on`, `polymorphic_identity` 等参数
- **Python 3.14 兼容**：包含针对 PEP 649 的兼容性修复

### TableBaseMixin

数据库表 Mixin，位于 `models.mixin.table`，继承后自动设置 `table=True`。

包含以下公共字段：

| 字段 | 类型 | 说明 |
|------|------|------|
| `id` | `int` | 自增主键 |
| `created_at` | `datetime` | 创建时间 |
| `updated_at` | `datetime` | 更新时间（自动更新） |

提供的 CRUD 方法：
- `add()` - 新增记录（类方法）
- `save()` - 保存实例（**必须使用返回值**）
- `update()` - 更新记录（**必须使用返回值**）
- `delete()` - 删除记录
- `get()` - 查询记录（类方法，支持分页、排序、时间筛选、多态加载）
- `get_with_count()` - 分页查询并返回总数（类方法，返回 `ListResponse[T]`）
- `get_exist_one()` - 获取存在的记录（不存在则抛出 404）
- `count()` - 统计记录数（类方法，支持时间筛选）

分页排序请求类：
- `TimeFilterRequest` - 时间筛选参数
- `PaginationRequest` - 分页排序参数
- `TableViewRequest` - 组合分页排序和时间筛选

**使用方式**：
```python
from models.base import SQLModelBase
from models.mixin import TableBaseMixin

class MyModel(SQLModelBase, TableBaseMixin):
    name: str
```

### UUIDTableBaseMixin

继承自 TableBaseMixin，将主键改为 UUID 类型：

| 字段 | 类型 | 说明 |
|------|------|------|
| `id` | `UUID` | UUID 主键（自动生成） |

**使用方式**：
```python
from models.base import SQLModelBase
from models.mixin import UUIDTableBaseMixin

class MyUUIDModel(SQLModelBase, UUIDTableBaseMixin):
    name: str
```

**注意**：当有 Base 类已继承 SQLModelBase 时，子类不需要重复继承：
```python
class UserBase(SQLModelBase):
    username: str

class User(UserBase, UUIDTableBaseMixin):  # 不需要再写 SQLModelBase
    password: str
```

### ListResponse[T]

泛型分页响应类，用于所有 LIST 端点的标准化响应格式：

```python
class ListResponse(BaseModel, Generic[ItemT]):
    count: int      # 符合条件的记录总数
    items: list[T]  # 当前页的记录列表
```

**使用示例**：
```python
@router.get("", response_model=ListResponse[UserResponse])
async def list_users(session: SessionDep, table_view: TableViewRequestDep):
    return await User.get_with_count(session, table_view=table_view)
```

---

## 数据库表模型

### 1. User（用户）

**表名**: `user`
**基类**: `UUIDTableBaseMixin`

| 字段 | 类型 | 说明 |
|------|------|------|
| `id` | `UUID` | 用户 UUID（主键） |
| `username` | `str` | 用户名，唯一，不可更改 |
| `nickname` | `str?` | 用户昵称 |
| `password` | `str` | 密码（Argon2 加密） |
| `status` | `UserStatus` | 用户状态：active/admin_banned/system_banned |
| `storage` | `int` | 已用存储空间（字节） |
| `two_factor` | `str?` | 两步验证密钥（TOTP） |
| `avatar` | `str` | 头像类型/地址 |
| `score` | `int` | 用户积分 |
| `group_expires` | `datetime?` | 当前用户组过期时间 |
| `theme` | `ThemeType` | 主题类型：light/dark/system |
| `language` | `str` | 语言偏好（默认 zh-CN） |
| `timezone` | `int` | 时区 UTC 偏移（-12 ~ 12） |
| `group_id` | `UUID` | 所属用户组（外键） |
| `previous_group_id` | `UUID?` | 之前的用户组（用于过期后恢复） |

**关系**:
- `group`: 所属用户组
- `previous_group`: 之前的用户组（用于过期后恢复）
- `tags`: 用户的标签列表
- `authns`: 用户的 WebAuthn 凭证列表

---

### 2. UserAuthn（WebAuthn 凭证）

**表名**: `userauthn`
**基类**: `TableBaseMixin`

| 字段 | 类型 | 说明 |
|------|------|------|
| `id` | `int` | 主键 |
| `credential_id` | `str` | 凭证 ID（Base64 编码） |
| `credential_public_key` | `str` | 凭证公钥（Base64 编码） |
| `sign_count` | `int` | 签名计数器（防重放） |
| `credential_device_type` | `str` | 设备类型：single_device/multi_device |
| `credential_backed_up` | `bool` | 凭证是否已备份 |
| `transports` | `str?` | 支持的传输方式（逗号分隔） |
| `name` | `str?` | 用户自定义凭证名称 |
| `user_id` | `UUID` | 所属用户（外键） |

---

### 3. Group（用户组）

**表名**: `group`
**基类**: `UUIDTableBaseMixin`

| 字段 | 类型 | 说明 |
|------|------|------|
| `id` | `UUID` | 用户组 UUID（主键） |
| `name` | `str` | 用户组名称，唯一 |
| `max_storage` | `int` | 最大存储空间（字节） |
| `share_enabled` | `bool` | 是否允许创建分享 |
| `web_dav_enabled` | `bool` | 是否允许使用 WebDAV |
| `admin` | `bool` | 是否为管理员组 |
| `speed_limit` | `int` | 速度限制（KB/s），0 为不限制 |

---

### 4. GroupOptions（用户组选项）

**表名**: `groupoptions`
**基类**: `TableBaseMixin`

| 字段 | 类型 | 说明 |
|------|------|------|
| `id` | `int` | 主键 |
| `group_id` | `UUID` | 关联的用户组（外键，唯一） |
| `share_download` | `bool` | 是否允许分享下载 |
| `share_free` | `bool` | 是否免积分获取内容 |
| `relocate` | `bool` | 是否允许文件重定位 |
| `source_batch` | `int` | 批量获取源地址数量 |
| `select_node` | `bool` | 是否允许选择节点 |
| `advance_delete` | `bool` | 是否允许高级删除 |
| `archive_download` | `bool` | 是否允许打包下载 |
| `archive_task` | `bool` | 是否允许创建打包任务 |
| `webdav_proxy` | `bool` | 是否允许 WebDAV 代理 |
| `aria2` | `bool` | 是否允许使用 aria2 |
| `redirected_source` | `bool` | 是否使用重定向源 |

---

### 5. GroupPolicyLink（用户组-策略关联）

**表名**: `grouppolicylink`
**基类**: `SQLModelBase`（关联表）

| 字段 | 类型 | 说明 |
|------|------|------|
| `group_id` | `UUID` | 用户组（复合主键） |
| `policy_id` | `UUID` | 存储策略（复合主键） |

---

### 6. Policy（存储策略）

**表名**: `policy`
**基类**: `UUIDTableBaseMixin`

| 字段 | 类型 | 说明 |
|------|------|------|
| `id` | `UUID` | 策略 UUID（主键） |
| `name` | `str` | 策略名称，唯一 |
| `type` | `PolicyType` | 策略类型：local/s3 |
| `server` | `str?` | 服务器地址 |
| `bucket_name` | `str?` | 存储桶名称 |
| `is_private` | `bool` | 是否为私有空间 |
| `base_url` | `str?` | 访问文件的基础 URL |
| `access_key` | `str?` | Access Key |
| `secret_key` | `str?` | Secret Key |
| `max_size` | `int` | 允许上传的最大文件尺寸（字节） |
| `auto_rename` | `bool` | 是否自动重命名 |
| `dir_name_rule` | `str?` | 目录命名规则 |
| `file_name_rule` | `str?` | 文件命名规则 |
| `is_origin_link_enable` | `bool` | 是否开启源链接访问 |

**关系**:
- `options`: 一对一关联 PolicyOptions

---

### 7. PolicyOptions（存储策略选项）

**表名**: `policyoptions`
**基类**: `UUIDTableBaseMixin`

| 字段 | 类型 | 说明 |
|------|------|------|
| `id` | `UUID` | 主键 |
| `policy_id` | `UUID` | 关联的策略（外键，唯一） |
| `token` | `str?` | 访问令牌 |
| `file_type` | `str?` | 允许的文件类型 |
| `mimetype` | `str?` | MIME 类型 |
| `od_redirect` | `str?` | OneDrive 重定向地址 |
| `chunk_size` | `int` | 分片上传大小（字节），默认 50MB |
| `s3_path_style` | `bool` | 是否使用 S3 路径风格 |

---

### 8. PhysicalFile（物理文件）

**表名**: `physicalfile`
**基类**: `UUIDTableBaseMixin`

表示磁盘上的实际文件。多个 Object 可以引用同一个 PhysicalFile，实现文件共享而不复制物理文件。

| 字段 | 类型 | 说明 |
|------|------|------|
| `id` | `UUID` | 物理文件 UUID（主键） |
| `storage_path` | `str` | 物理存储路径（相对于存储策略根目录） |
| `size` | `int` | 文件大小（字节） |
| `checksum_md5` | `str?` | MD5 校验和（用于文件去重和完整性校验） |
| `policy_id` | `UUID` | 存储策略（外键） |
| `reference_count` | `int` | 引用计数（有多少个 Object 引用此物理文件） |

**索引**:
- `ix_physical_file_policy_path`: (policy_id, storage_path)
- `ix_physical_file_checksum`: (checksum_md5)

**关系**:
- `policy`: 存储策略
- `objects`: 引用此物理文件的所有逻辑对象（一对多）

**业务方法**:
- `increment_reference()`: 增加引用计数
- `decrement_reference()`: 减少引用计数
- `can_be_deleted`: 属性，是否可物理删除（引用计数为 0）

---

### 9. Object（统一对象）

**表名**: `object`
**基类**: `UUIDTableBaseMixin`

合并了文件和目录，通过 `type` 字段区分。

| 字段 | 类型 | 说明 |
|------|------|------|
| `id` | `UUID` | 对象 UUID（主键） |
| `name` | `str` | 对象名称（文件名或目录名） |
| `type` | `ObjectType` | 对象类型：file/folder |
| `password` | `str?` | 对象独立密码 |
| `size` | `int` | 文件大小（字节），目录为 0 |
| `upload_session_id` | `str?` | 分块上传会话 ID |
| `physical_file_id` | `UUID?` | 关联的物理文件（仅文件有效，目录为 NULL） |
| `parent_id` | `UUID?` | 父目录（外键，NULL 表示根目录） |
| `owner_id` | `UUID` | 所有者用户（外键） |
| `policy_id` | `UUID` | 存储策略（外键） |
| `is_banned` | `bool` | 是否被封禁 |
| `banned_at` | `datetime?` | 封禁时间 |
| `banned_by` | `UUID?` | 封禁操作者 UUID |
| `ban_reason` | `str?` | 封禁原因 |

**约束**:
- 同一父目录下名称唯一（owner_id + parent_id + name）
- 名称不能包含斜杠

**索引**:
- `ix_object_owner_updated`: (owner_id, updated_at)
- `ix_object_parent_updated`: (parent_id, updated_at)
- `ix_object_owner_type`: (owner_id, type)
- `ix_object_owner_size`: (owner_id, size)

**关系**:
- `file_metadata`: 一对一关联 FileMetadata
- `physical_file`: 关联的物理文件（仅文件有效）
- `owner`: 所有者用户
- `banner`: 封禁操作者
- `parent`: 父目录（自引用）
- `children`: 子对象列表（自引用）
- `source_links`: 源链接列表
- `shares`: 分享列表
- `policy`: 存储策略

**业务属性**:
- `source_name`: 向后兼容属性，返回物理文件的存储路径
- `is_file`: 是否为文件
- `is_folder`: 是否为目录

**类方法**:
- `get_by_path()`: 根据路径获取对象
- `get_children()`: 获取子对象列表

---

### 10. FileMetadata（文件元数据）

**表名**: `filemetadata`
**基类**: `UUIDTableBaseMixin`

| 字段 | 类型 | 说明 |
|------|------|------|
| `id` | `UUID` | 主键 |
| `object_id` | `UUID` | 关联的对象（外键，唯一） |
| `width` | `int?` | 图片/视频宽度（像素） |
| `height` | `int?` | 图片/视频高度（像素） |
| `duration` | `float?` | 音视频时长（秒） |
| `bitrate` | `int?` | 比特率（kbps） |
| `mime_type` | `str?` | MIME 类型 |
| `checksum_md5` | `str?` | MD5 校验和 |
| `checksum_sha256` | `str?` | SHA256 校验和 |

**关系**:
- `object`: 关联的 Object（一对一）

---

### 11. UploadSession（上传会话）

**表名**: `uploadsession`
**基类**: `UUIDTableBaseMixin`

用于管理分片上传的会话状态。会话有效期为 24 小时，过期后自动失效。

| 字段 | 类型 | 说明 |
|------|------|------|
| `id` | `UUID` | 会话 UUID（主键） |
| `file_name` | `str` | 原始文件名 |
| `file_size` | `int` | 文件总大小（字节） |
| `chunk_size` | `int` | 分片大小（字节） |
| `total_chunks` | `int` | 总分片数 |
| `uploaded_chunks` | `int` | 已上传分片数 |
| `uploaded_size` | `int` | 已上传大小（字节） |
| `storage_path` | `str?` | 文件存储路径 |
| `expires_at` | `datetime` | 会话过期时间 |
| `owner_id` | `UUID` | 上传者用户（外键） |
| `parent_id` | `UUID` | 目标父目录（外键） |
| `policy_id` | `UUID` | 存储策略（外键） |

**关系**:
- `owner`: 上传者用户
- `parent`: 目标父目录
- `policy`: 存储策略

**业务属性**:
- `is_expired`: 会话是否已过期
- `is_complete`: 上传是否完成

---

### 12. SourceLink（源链接）

**表名**: `sourcelink`
**基类**: `TableBaseMixin`

| 字段 | 类型 | 说明 |
|------|------|------|
| `id` | `int` | 主键 |
| `name` | `str` | 链接名称 |
| `downloads` | `int` | 通过此链接的下载次数 |
| `object_id` | `UUID` | 关联的对象（外键，必须是文件） |

---

### 13. Share（分享）

**表名**: `share`
**基类**: `TableBaseMixin`

| 字段 | 类型 | 说明 |
|------|------|------|
| `id` | `int` | 主键 |
| `code` | `str` | 分享码，唯一 |
| `password` | `str?` | 分享密码（加密后） |
| `object_id` | `UUID` | 关联的对象（外键） |
| `views` | `int` | 浏览次数 |
| `downloads` | `int` | 下载次数 |
| `remain_downloads` | `int?` | 剩余下载次数（NULL 为不限制） |
| `expires` | `datetime?` | 过期时间（NULL 为永不过期） |
| `preview_enabled` | `bool` | 是否允许预览 |
| `source_name` | `str?` | 源名称（冗余字段） |
| `score` | `int` | 兑换所需积分 |
| `user_id` | `UUID` | 创建分享的用户（外键） |

---

### 14. Report（举报）

**表名**: `report`
**基类**: `TableBaseMixin`

| 字段 | 类型 | 说明 |
|------|------|------|
| `id` | `int` | 主键 |
| `reason` | `int` | 举报原因代码 |
| `description` | `str?` | 补充描述 |
| `share_id` | `int` | 被举报的分享（外键） |

---

### 15. Tag（标签）

**表名**: `tag`
**基类**: `TableBaseMixin`

| 字段 | 类型 | 说明 |
|------|------|------|
| `id` | `int` | 主键 |
| `name` | `str` | 标签名称 |
| `icon` | `str?` | 标签图标 |
| `color` | `str?` | 标签颜色 |
| `type` | `TagType` | 标签类型：manual/automatic |
| `expression` | `str?` | 自动标签的匹配表达式 |
| `user_id` | `UUID` | 所属用户（外键） |

**约束**: 同一用户下标签名称唯一

---

### 16. Task（任务）

**表名**: `task`
**基类**: `TableBaseMixin`

| 字段 | 类型 | 说明 |
|------|------|------|
| `id` | `int` | 主键 |
| `status` | `TaskStatus` | 任务状态：queued/running/completed/error |
| `type` | `int` | 任务类型（[TODO] 待定义枚举） |
| `progress` | `int` | 任务进度（0-100） |
| `error` | `str?` | 错误信息 |
| `user_id` | `UUID` | 所属用户（外键） |

**索引**: `ix_task_status`, `ix_task_user_status`

**关系**:
- `props`: 一对一关联 TaskProps
- `downloads`: 一对多关联 Download

---

### 17. TaskProps（任务属性）

**表名**: `taskprops`
**基类**: `TableBaseMixin`（主键为外键 task_id）

| 字段 | 类型 | 说明 |
|------|------|------|
| `task_id` | `int` | 关联的任务（外键，主键） |
| `source_path` | `str?` | 源路径 |
| `dest_path` | `str?` | 目标路径 |
| `file_ids` | `str?` | 文件ID列表（逗号分隔） |

---

### 18. Download（离线下载）

**表名**: `download`
**基类**: `UUIDTableBaseMixin`

| 字段 | 类型 | 说明 |
|------|------|------|
| `id` | `UUID` | 主键 |
| `status` | `DownloadStatus` | 下载状态：running/completed/error |
| `type` | `int` | 任务类型（[TODO] 待定义枚举） |
| `source` | `str` | 来源 URL 或标识 |
| `total_size` | `int` | 总大小（字节） |
| `downloaded_size` | `int` | 已下载大小（字节） |
| `g_id` | `str?` | Aria2 GID |
| `speed` | `int` | 下载速度（bytes/s） |
| `parent` | `str?` | 父任务标识 |
| `error` | `str?` | 错误信息 |
| `dst` | `str` | 目标存储路径 |
| `user_id` | `UUID` | 所属用户（外键） |
| `task_id` | `int?` | 关联的任务（外键） |
| `node_id` | `int` | 执行下载的节点（外键） |

**约束**: 同一节点下 g_id 唯一

**索引**: `ix_download_status`, `ix_download_user_status`

**关系**:
- `aria2_info`: 一对一关联 DownloadAria2Info
- `aria2_files`: 一对多关联 DownloadAria2File

---

### 19. DownloadAria2Info（Aria2下载信息）

**表名**: `downloadaria2info`
**基类**: `TableBaseMixin`（主键为外键 download_id）

| 字段 | 类型 | 说明 |
|------|------|------|
| `download_id` | `UUID` | 关联的下载任务（外键，主键） |
| `info_hash` | `str?` | InfoHash（BT种子） |
| `piece_length` | `int` | 分片大小 |
| `num_pieces` | `int` | 分片数量 |
| `num_seeders` | `int` | 做种人数 |
| `connections` | `int` | 连接数 |
| `upload_speed` | `int` | 上传速度（bytes/s） |
| `upload_length` | `int` | 已上传大小（字节） |
| `error_code` | `str?` | 错误代码 |
| `error_message` | `str?` | 错误信息 |

---

### 20. DownloadAria2File（Aria2下载文件）

**表名**: `downloadaria2file`
**基类**: `TableBaseMixin`

| 字段 | 类型 | 说明 |
|------|------|------|
| `id` | `int` | 主键 |
| `download_id` | `UUID` | 关联的下载任务（外键） |
| `file_index` | `int` | 文件索引（从1开始） |
| `path` | `str` | 文件路径 |
| `length` | `int` | 文件大小（字节） |
| `completed_length` | `int` | 已完成大小（字节） |
| `is_selected` | `bool` | 是否选中下载 |

---

### 21. Node（节点）

**表名**: `node`
**基类**: `TableBaseMixin`

| 字段 | 类型 | 说明 |
|------|------|------|
| `id` | `int` | 主键 |
| `status` | `NodeStatus` | 节点状态：online/offline |
| `name` | `str` | 节点名称，唯一 |
| `type` | `int` | 节点类型（[TODO] 待定义枚举） |
| `server` | `str` | 节点地址（IP 或域名） |
| `slave_key` | `str?` | 从机通讯密钥 |
| `master_key` | `str?` | 主机通讯密钥 |
| `aria2_enabled` | `bool` | 是否启用 Aria2 |
| `rank` | `int` | 节点排序权重 |

**索引**: `ix_node_status`

**关系**:
- `aria2_config`: 一对一关联 Aria2Configuration
- `downloads`: 一对多关联 Download

---

### 22. Aria2Configuration（Aria2配置）

**表名**: `aria2configuration`
**基类**: `TableBaseMixin`

| 字段 | 类型 | 说明 |
|------|------|------|
| `id` | `int` | 主键 |
| `node_id` | `int` | 关联的节点（外键，唯一） |
| `rpc_url` | `str?` | RPC地址 |
| `rpc_secret` | `str?` | RPC密钥 |
| `temp_path` | `str?` | 临时下载路径 |
| `max_concurrent` | `int` | 最大并发数（1-50，默认5） |
| `timeout` | `int` | 请求超时时间（秒，默认300） |

---

### 23. Order（订单）

**表名**: `order`
**基类**: `TableBaseMixin`

| 字段 | 类型 | 说明 |
|------|------|------|
| `id` | `int` | 主键 |
| `order_no` | `str` | 订单号，唯一 |
| `type` | `int` | 订单类型（[TODO] 待定义枚举） |
| `method` | `str?` | 支付方式 |
| `product_id` | `int?` | 商品 ID |
| `num` | `int` | 购买数量 |
| `name` | `str` | 商品名称 |
| `price` | `int` | 订单价格（分） |
| `status` | `OrderStatus` | 订单状态：pending/completed/cancelled |
| `user_id` | `UUID` | 所属用户（外键） |

---

### 24. Redeem（兑换码）

**表名**: `redeem`
**基类**: `TableBaseMixin`

| 字段 | 类型 | 说明 |
|------|------|------|
| `id` | `int` | 主键 |
| `type` | `int` | 兑换码类型（[TODO] 待定义枚举） |
| `product_id` | `int?` | 关联的商品/权益 ID |
| `num` | `int` | 可兑换数量/时长等 |
| `code` | `str` | 兑换码，唯一 |
| `used` | `bool` | 是否已使用 |

---

### 25. StoragePack（容量包）

**表名**: `storagepack`
**基类**: `TableBaseMixin`

| 字段 | 类型 | 说明 |
|------|------|------|
| `id` | `int` | 主键 |
| `name` | `str` | 容量包名称 |
| `active_time` | `datetime?` | 激活时间 |
| `expired_time` | `datetime?` | 过期时间 |
| `size` | `int` | 容量包大小（字节） |
| `user_id` | `UUID` | 所属用户（外键） |

---

### 26. WebDAV（WebDAV 账户）

**表名**: `webdav`
**基类**: `TableBaseMixin`

| 字段 | 类型 | 说明 |
|------|------|------|
| `id` | `int` | 主键 |
| `name` | `str` | WebDAV 账户名 |
| `password` | `str` | WebDAV 密码 |
| `root` | `str` | 根目录路径（默认 /） |
| `readonly` | `bool` | 是否只读 |
| `use_proxy` | `bool` | 是否使用代理下载 |
| `user_id` | `UUID` | 所属用户（外键） |

**约束**: 同一用户下账户名唯一

---

### 27. Setting（系统设置）

**表名**: `setting`
**基类**: `TableBaseMixin`

| 字段 | 类型 | 说明 |
|------|------|------|
| `id` | `int` | 主键 |
| `type` | `SettingsType` | 设置类型/分组 |
| `name` | `str` | 设置项名称 |
| `value` | `str?` | 设置值 |

**约束**: type + name 唯一

**SettingsType 枚举值**:
`aria2`, `auth`, `authn`, `avatar`, `basic`, `captcha`, `cron`, `file_edit`, `login`, `mail`, `mail_template`, `mobile`, `path`, `preview`, `pwa`, `register`, `retry`, `share`, `slave`, `task`, `thumb`, `timeout`, `upload`, `version`, `view`, `wopi`

---

## 模型关系图

### 一对一关系

```
┌───────────────────────────────────────────────────────────────────┐
│                         一对一关系                                 │
├───────────────────────────────────────────────────────────────────┤
│                                                                   │
│   Group ◄─────────────────────────> GroupOptions                  │
│          group_id (unique FK)                                     │
│                                                                   │
│   Policy ◄────────────────────────> PolicyOptions                 │
│          policy_id (unique FK)                                    │
│                                                                   │
│   Object ◄────────────────────────> FileMetadata                  │
│          object_id (unique FK)                                    │
│                                                                   │
│   Node ◄──────────────────────────> Aria2Configuration            │
│          node_id (unique FK)                                      │
│                                                                   │
│   Task ◄──────────────────────────> TaskProps                     │
│          task_id (PK/FK)                                          │
│                                                                   │
│   Download ◄──────────────────────> DownloadAria2Info             │
│          download_id (PK/FK)                                      │
│                                                                   │
└───────────────────────────────────────────────────────────────────┘
```

**新增关系**:
```
┌───────────────────────────────────────────────────────────────────┐
│                     一对多关系（新增）                              │
├───────────────────────────────────────────────────────────────────┤
│                                                                   │
│   PhysicalFile ◄──────────────────> Object (多个)                 │
│          physical_file_id (FK)      文件去重：多个Object可引用    │
│                                     同一个PhysicalFile            │
│                                                                   │
│   User ◄──────────────────────────> UploadSession                 │
│          owner_id (FK)              用户的上传会话列表            │
│                                                                   │
└───────────────────────────────────────────────────────────────────┘
```

| 主表 | 从表 | 外键 | 说明 |
|------|------|------|------|
| Group | GroupOptions | `group_id` (unique) | 每个用户组有且仅有一个选项配置 |
| Policy | PolicyOptions | `policy_id` (unique) | 每个存储策略有且仅有一个扩展选项 |
| Object | FileMetadata | `object_id` (unique) | 每个文件对象有且仅有一个元数据 |
| Node | Aria2Configuration | `node_id` (unique) | 每个节点有且仅有一个 Aria2 配置 |
| Task | TaskProps | `task_id` (PK) | 每个任务有且仅有一个属性配置 |
| Download | DownloadAria2Info | `download_id` (PK) | 每个下载任务有且仅有一个 Aria2 信息 |

---

### 一对多关系

```
┌──────────────────────────────────────────────────────────────────────────────┐
│                                 一对多关系                                   │
├──────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│                         ┌──────> Download                                    │
│                         │                                                    │
│                         ├──────> Object ◄──────┬──────> SourceLink           │
│                         │         │ ↑          │                             │
│                         │         │ │          └──────> Share ──────> Report │
│   Group ──────> User ───┼─────────┘ │                                        │
│     │                   │           │ (自引用：parent-children)              │
│     │                   ├──────> Order                                       │
│     │                   │                                                    │
│     │                   ├──────> StoragePack                                 │
│     │                   │                                                    │
│     │                   ├──────> Tag                                         │
│     │                   │                                                    │
│     │                   ├──────> Task ──────> Download                       │
│     │                   │                        ↑                           │
│     │                   ├──────> WebDAV          │                           │
│     │                   │                        │                           │
│     │                   └──────> UserAuthn       │                           │
│     │                                            │                           │
│     └──────> Policy ──────> Object               │                           │
│                                                  │                           │
│                              Node ───────────────┘                           │
│                                                                              │
└──────────────────────────────────────────────────────────────────────────────┘
```

| 一端 | 多端 | 外键 | 说明 |
|------|------|------|------|
| **Group** | User | `group_id` | 用户组包含多个用户 |
| **Group** | User | `previous_group_id` | 用户组过期后恢复关系 |
| **User** | Download | `user_id` | 用户的离线下载任务 |
| **User** | Object | `owner_id` | 用户拥有的文件/目录 |
| **User** | Order | `user_id` | 用户的订单 |
| **User** | Share | `user_id` | 用户创建的分享 |
| **User** | StoragePack | `user_id` | 用户的容量包 |
| **User** | Tag | `user_id` | 用户的标签 |
| **User** | Task | `user_id` | 用户的任务 |
| **User** | WebDAV | `user_id` | 用户的 WebDAV 账户 |
| **User** | UserAuthn | `user_id` | 用户的 WebAuthn 凭证 |
| **User** | UploadSession | `owner_id` | 用户的上传会话 |
| **Policy** | Object | `policy_id` | 存储策略下的对象 |
| **Policy** | PhysicalFile | `policy_id` | 存储策略下的物理文件 |
| **PhysicalFile** | Object | `physical_file_id` | 物理文件被多个逻辑对象引用（文件去重） |
| **Object** | Object | `parent_id` | 目录的子文件/子目录（自引用） |
| **Object** | SourceLink | `object_id` | 文件的源链接 |
| **Object** | Share | `object_id` | 对象的分享 |
| **Share** | Report | `share_id` | 分享的举报 |
| **Task** | Download | `task_id` | 任务关联的下载 |
| **Node** | Download | `node_id` | 节点执行的下载任务 |
| **Download** | DownloadAria2File | `download_id` | 下载任务的文件列表 |

---

### 多对多关系

```
┌─────────────────────────────────────────────────────────┐
│                      多对多关系                         │
├─────────────────────────────────────────────────────────┤
│                                                         │
│   Group ◄────── GroupPolicyLink ──────> Policy          │
│                                                         │
│   - 一个用户组可以使用多个存储策略                      │
│   - 一个存储策略可以被多个用户组使用                    │
│                                                         │
└─────────────────────────────────────────────────────────┘
```

| 表1 | 表2 | 关联表 | 说明 |
|-----|-----|--------|------|
| Group | Policy | GroupPolicyLink | 用户组可使用的存储策略 |

---

## 完整关系 ER 图

```
                                    ┌──────────────┐
                                    │   Setting    │
                                    │   (独立表)   │
                                    └──────────────┘

                                    ┌──────────────┐
                                    │    Redeem    │
                                    │   (独立表)   │
                                    └──────────────┘

┌──────────────┐     1:1      ┌──────────────┐
│    Group     │◄────────────>│ GroupOptions │
│              │              └──────────────┘
│              │
│              │──────┐ M:N   ┌──────────────────┐
│              │      └──────>│ GroupPolicyLink  │◄───┐
└──────┬───────┘              └──────────────────┘    │
       │                                              │
       │ 1:N                                          │
       ▼                                              │
┌──────────────┐              ┌──────────────┐        │
│     User     │              │    Policy    │◄───────┘
│              │              │              │
│              │              │              │◄────────────>┌───────────────┐
│              │              └──────┬───────┘     1:1      │ PolicyOptions │
│              │                     │ 1:N                  └───────────────┘
│              │──────────────┐      │
└──────┬───────┘              │      │
       │                      │      ▼
       │ 1:N                  │ ┌──────────────┐      ┌──────────────┐
       │                      │ │    Object    │◄────>│    Object    │
       │                      │ │              │      │  (children)  │
       │                      │ │              │      └──────────────┘
       ├──────────────────────┼─┤              │
       │                      │ └──────┬───────┘
       │                      │        │
       │                      │        │ 1:N          ┌──────────────┐
       │                      │        ├─────────────>│  SourceLink  │
       │                      │        │              └──────────────┘
       │                      │        │              
       │                      │        │
       │                      │        │ 1:N          ┌──────────────┐
       │                      │        └─────────────>│     Share    │─────> Report
       │                      │                       └──────────────┘
       │                      │                       
       │                      │
       ├──> Download ◄────────┼───────────────────────── Task
       │        ▲             │
       │        │             │
       │        │             │
       │        └─────────────┼─────────────────────── Node
       │                      │
       ├──> Order             │
       │                      │
       ├──> StoragePack       │
       │                      │
       ├──> Tag               │
       │                      │
       ├──> WebDAV            │
       │                      │
       └──> UserAuthn         │
                              │
                              │
```

---

## 枚举类型

### ObjectType
```python
class ObjectType(StrEnum):
    FILE = "file"      # 文件
    FOLDER = "folder"  # 目录
```

### PolicyType
```python
class PolicyType(StrEnum):
    LOCAL = "local"  # 本地存储
    S3 = "s3"        # S3 兼容存储
```

### StorageType
```python
class StorageType(StrEnum):
    LOCAL = "local"              # 本地存储
    QINIU = "qiniu"              # 七牛云
    TENCENT = "tencent"          # 腾讯云
    ALIYUN = "aliyun"            # 阿里云
    ONEDRIVE = "onedrive"        # OneDrive
    GOOGLE_DRIVE = "google_drive"  # Google Drive
    DROPBOX = "dropbox"          # Dropbox
    WEBDAV = "webdav"            # WebDAV
    REMOTE = "remote"            # 远程存储
```

### UserStatus
```python
class UserStatus(StrEnum):
    ACTIVE = "active"              # 正常
    ADMIN_BANNED = "admin_banned"  # 管理员封禁
    SYSTEM_BANNED = "system_banned"  # 系统封禁
```

### CaptchaType
```python
class CaptchaType(StrEnum):
    DEFAULT = "default"                      # 默认验证码
    GCAPTCHA = "gcaptcha"                    # Google reCAPTCHA
    CLOUD_FLARE_TURNSTILE = "cloudflare turnstile"  # Cloudflare Turnstile
```

### ThemeType
```python
class ThemeType(StrEnum):
    LIGHT = "light"    # 浅色主题
    DARK = "dark"      # 深色主题
    SYSTEM = "system"  # 跟随系统
```

### AvatarType
```python
class AvatarType(StrEnum):
    DEFAULT = "default"    # 默认头像
    GRAVATAR = "gravatar"  # Gravatar
    FILE = "file"          # 自定义文件
```

### TagType
```python
class TagType(StrEnum):
    MANUAL = "manual"        # 手动标签
    AUTOMATIC = "automatic"  # 自动标签
```

### TaskStatus
```python
class TaskStatus(StrEnum):
    QUEUED = "queued"        # 排队中
    RUNNING = "running"      # 处理中
    COMPLETED = "completed"  # 已完成
    ERROR = "error"          # 错误
```

### DownloadStatus
```python
class DownloadStatus(StrEnum):
    RUNNING = "running"      # 进行中
    COMPLETED = "completed"  # 已完成
    ERROR = "error"          # 错误
```

### NodeStatus
```python
class NodeStatus(StrEnum):
    ONLINE = "online"    # 正常
    OFFLINE = "offline"  # 离线
```

### OrderStatus
```python
class OrderStatus(StrEnum):
    PENDING = "pending"      # 待支付
    COMPLETED = "completed"  # 已完成
    CANCELLED = "cancelled"  # 已取消
```

### 待定义枚举（[TODO]）

以下枚举已定义框架，具体值待业务需求确定：

- `TaskType` - 任务类型
- `DownloadType` - 下载类型
- `NodeType` - 节点类型
- `OrderType` - 订单类型
- `RedeemType` - 兑换码类型
- `ReportReason` - 举报原因

---

## DTO 模型

### 用户相关

| DTO | 说明 |
|-----|------|
| `LoginRequest` | 登录请求 |
| `RegisterRequest` | 注册请求 |
| `TokenResponse` | 访问令牌响应（access_token, refresh_token, expires_in） |
| `UserResponse` | 用户信息响应（包含 group） |
| `UserPublic` | 用户公开信息 |
| `UserSettingResponse` | 用户设置响应 |
| `WebAuthnInfo` | WebAuthn 信息 |
| `AuthnResponse` | WebAuthn 响应 |
| `UserAdminUpdateRequest` | 管理员更新用户请求 |
| `UserCalibrateResponse` | 用户存储校准响应 |
| `UserAdminDetailResponse` | 管理员用户详情响应 |

### 用户组相关

| DTO | 说明 |
|-----|------|
| `GroupBase` | 用户组基础字段 |
| `GroupOptionsBase` | 用户组选项基础字段 |
| `GroupAllOptionsBase` | 用户组所有选项基础字段 |
| `GroupResponse` | 用户组响应（包含 options） |
| `GroupCreateRequest` | 管理员创建用户组请求 |
| `GroupUpdateRequest` | 管理员更新用户组请求 |
| `GroupDetailResponse` | 管理员用户组详情响应 |
| `GroupListResponse` | 用户组列表响应 |

### 存储策略相关

| DTO | 说明 |
|-----|------|
| `PolicyBase` | 存储策略基础字段 |
| `PolicyOptionsBase` | 存储策略选项基础字段 |
| `PolicyResponse` | 存储策略响应（id, name, type, max_size） |
| `PolicySummary` | 存储策略摘要 |

### 对象相关

| DTO | 说明 |
|-----|------|
| `ObjectBase` | 对象基础字段 |
| `ObjectResponse` | 对象响应（目录列表中的单个项） |
| `DirectoryCreateRequest` | 创建目录请求（parent_id, name, policy_id?） |
| `DirectoryResponse` | 目录响应（id, parent, objects, policy） |
| `ObjectMoveRequest` | 移动对象请求（src_ids, dst_id） |
| `ObjectDeleteRequest` | 删除对象请求（ids） |
| `ObjectCopyRequest` | 复制对象请求（src_ids, dst_id） |
| `ObjectRenameRequest` | 重命名对象请求（id, new_name） |
| `ObjectPropertyResponse` | 对象基本属性响应 |
| `ObjectPropertyDetailResponse` | 对象详细属性响应（含元数据、分享统计） |

### 上传相关

| DTO | 说明 |
|-----|------|
| `CreateUploadSessionRequest` | 创建上传会话请求（file_name, file_size, parent_id） |
| `UploadSessionResponse` | 上传会话响应（id, chunk_size, total_chunks） |
| `UploadChunkResponse` | 上传分片响应（uploaded_chunks, is_complete） |
| `CreateFileRequest` | 创建空白文件请求 |

### 管理员文件管理

| DTO | 说明 |
|-----|------|
| `AdminFileResponse` | 管理员文件响应 |
| `FileBanRequest` | 文件封禁请求 |
| `AdminFileListResponse` | 管理员文件列表响应 |

### 管理员概况

| DTO | 说明 |
|-----|------|
| `MetricsSummary` | 统计摘要（日期列表、每日增量、总计） |
| `LicenseInfo` | 许可证信息 |
| `VersionInfo` | 版本信息 |
| `AdminSummaryData` | 管理员概况数据 |
| `AdminSummaryResponse` | 管理员概况响应 |

### 系统设置

| DTO | 说明 |
|-----|------|
| `SiteConfigResponse` | 站点配置响应 |
| `ThemeResponse` | 主题颜色响应 |
| `SettingItem` | 设置项（type, name, value） |
| `SettingsListResponse` | 设置列表响应 |
| `SettingsUpdateRequest` | 更新设置请求（settings[]） |
| `SettingsUpdateResponse` | 更新设置响应（updated, created） |

### 分享相关

| DTO | 说明 |
|-----|------|
| `ShareBase` | 分享基础字段 |
| `ShareCreateRequest` | 创建分享请求 |
| `ShareResponse` | 分享响应 |
| `AdminShareListItem` | 管理员分享列表项 |

### 任务相关

| DTO | 说明 |
|-----|------|
| `TaskPropsBase` | 任务属性基础字段 |
| `TaskSummary` | 任务摘要 |

### 通用响应

| DTO | 说明 |
|-----|------|
| `ResponseBase` | 通用响应基类（code, msg, data） |
| `ListResponse[T]` | 泛型分页响应（count, items） |
| `MCPBase` | MCP 基类 |
| `MCPRequestBase` | MCP 请求基类 |
| `MCPResponseBase` | MCP 响应基类 |

---

## 使用示例

### 查询用户及其关联数据

```python
from sqlalchemy.orm import selectinload

# 获取用户及其用户组
user = await User.get(
    session,
    User.id == user_id,
    load=User.group
)

# 获取用户的所有文件
objects = await Object.get(
    session,
    (Object.owner_id == user_id) & (Object.type == ObjectType.FILE),
    fetch_mode="all"
)

# 分页查询并返回总数
from models.mixin import TableViewRequest, ListResponse

table_view = TableViewRequest(offset=0, limit=20, desc=True, order="created_at")
result: ListResponse[User] = await User.get_with_count(session, table_view=table_view)
print(f"总数: {result.count}, 当前页: {len(result.items)}")
```

### 创建文件对象

```python
file = Object(
    name="example.txt",
    type=ObjectType.FILE,
    size=1024,
    owner_id=user.id,
    parent_id=folder.id,
    policy_id=policy.id,
    physical_file_id=physical_file.id,
)
file = await file.save(session)  # 必须使用返回值
```

### 多对多关系操作

```python
# 为用户组添加存储策略
from models import GroupPolicyLink

link = GroupPolicyLink(group_id=group.id, policy_id=policy.id)
session.add(link)
await session.commit()
```

### 文件上传流程

```python
# 1. 创建上传会话
upload_session = UploadSession(
    file_name="large_file.zip",
    file_size=104857600,  # 100MB
    chunk_size=52428800,  # 50MB
    total_chunks=2,
    owner_id=user.id,
    parent_id=folder.id,
    policy_id=policy.id,
)
upload_session = await upload_session.save(session)

# 2. 上传分片后更新进度
upload_session.uploaded_chunks += 1
upload_session.uploaded_size += chunk_size
upload_session = await upload_session.save(session)

# 3. 检查是否完成
if upload_session.is_complete:
    # 创建 PhysicalFile 和 Object 记录
    ...
```

### 文件引用计数（去重）

```python
# 复制文件时，只增加引用计数，不复制物理文件
if src.is_file and src.physical_file_id:
    physical_file = await PhysicalFile.get(session, PhysicalFile.id == src.physical_file_id)
    physical_file.increment_reference()
    await physical_file.save(session)

# 删除文件时，减少引用计数
physical_file.decrement_reference()
if physical_file.can_be_deleted:
    # 引用计数为0，可以删除物理文件
    await storage_service.delete_file(physical_file.storage_path)
    await PhysicalFile.delete(session, physical_file)
else:
    await physical_file.save(session)
```
