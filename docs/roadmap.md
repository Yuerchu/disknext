# DiskNext Roadmap

## 服务架构演进

### 现状

所有功能在 FastAPI 单体中运行，包括 REST API、WebDAV（WsgiDAV 同步桥接）、WOPI、
文件上传下载、S3 签名、存储迁移、打包下载等。

核心矛盾：**字节流密集型操作（上传/下载/签名/压缩/迁移）和业务逻辑（认证/CRUD/权限）
混在同一个 Python 进程中**，前者受 GIL 和异步桥接限制，后者才是 Python 擅长的。

### 目标架构：双服务拆分

```
Nginx / Traefik
│
├── /api/v1/*  ──→ ┌──────────────────────────────┐
├── /wopi/*    ──→ │  FastAPI (Python)             │
│                  │  - REST API / 认证 / 权限      │
│                  │  - 文件元数据 CRUD             │
│                  │  - WOPI 协议（轻量，3 端点）    │
│                  │  - 管理后台                    │
│                  └──────────────────────────────┘
│
├── /dav/*     ──→ ┌──────────────────────────────┐
├── /upload/*  ──→ │  Storage Gateway (Go)         │
├── /download/*──→ │  - WebDAV 协议                │
│                  │  - 文件上传（分片/直传）        │
│                  │  - 文件下载（直传/重定向）      │
│                  │  - S3 签名 & 代理              │
│                  │  - 存储迁移 Worker             │
│                  │  - 打包下载（ZIP/TAR）          │
│                  └──────────────────────────────┘
│
└── 共享：PostgreSQL + Redis + Local/S3 存储后端
```

**原则**：Python 管数据库和业务逻辑，Go 管字节流。

### 拆分理由

| 留在 Python | 拆到 Go | 不拆的理由 |
|------------|---------|-----------|
| REST API | WebDAV | — |
| 认证/权限 | 分片上传 | — |
| 用户/文件元数据 CRUD | 文件下载/流式传输 | — |
| 管理后台 | S3 HMAC-SHA256 签名 | — |
| WOPI（3 端点） | — | 流量低、逻辑简单 |
| 密码哈希 | — | argon2-cffi 是 C 实现 |
| Aria2 RPC 调用 | — | Aria2 本身是独立进程 |
| 元数据提取 | — | 尚未实现，等有了再评估 |

### 不做微服务的理由

按功能拆成 5-6 个微服务（WebDAV 服务、上传服务、下载服务、迁移 Worker、打包服务……）
运维成本过高。所有"跟字节流打交道"的功能特征一致（CPU+IO 密集、需要高并发、
直接操作存储后端），合并为一个 Go 服务足够。

---

## Storage Gateway (Go) 详细设计

### 职责清单

#### 1. WebDAV 协议

- Basic Auth 认证（复用 Redis WebDAVAuthCache 或直查 PG `webdav` 表）
- PROPFIND / PROPPATCH / MKCOL / GET / PUT / DELETE / MOVE / COPY / LOCK / UNLOCK
- 读写 PG `entry` 表构建文件树

#### 2. 文件上传

- 分片上传会话管理（创建/上传块/完成/取消）
- 本地存储：直接写入文件系统
- S3 存储：CreateMultipartUpload / UploadPart / CompleteMultipartUpload
- 上传完成后回调 FastAPI 更新元数据

#### 3. 文件下载

- 本地存储：直接 sendfile / FileResponse
- S3 存储：Presigned URL 重定向 或 代理下载
- Range 请求支持（断点续传）

#### 4. S3 签名代理

- AWS Signature V4 签名（Go 原生 crypto，性能远优于 Python hmac）
- Presigned URL 生成

#### 5. 存储迁移 Worker

- 从 Redis 队列消费迁移任务
- 文件在 Local ↔ S3 之间迁移
- 进度写入 PG `task` 表
- 失败自动重试

#### 6. 打包下载

- 流式 ZIP/TAR 生成（不在内存中缓冲整个归档）
- 递归遍历 `entry` 表收集文件列表
- 从 Local/S3 读取文件流逐个写入归档流

### 共享资源

| 资源 | 访问方式 | 注意事项 |
|------|---------|---------|
| PostgreSQL | `pgx` 直连 | 共享 entry/user/group/webdav/policy/physical_file 表 |
| Redis | `go-redis` 直连 | 共享认证缓存 key 格式、迁移任务队列 |
| Local 存储 | 共享挂载卷 | Docker 需配置相同 volume |
| S3 存储 | `aws-sdk-go-v2` | 相同 bucket、相同路径规则 |

### Go 技术选型

| 组件 | 库 |
|------|-----|
| HTTP 框架 | 标准库 `net/http` 或 `chi` |
| WebDAV | `golang.org/x/net/webdav` |
| PostgreSQL | `jackc/pgx/v5` |
| Redis | `redis/go-redis/v9` |
| S3 | `aws/aws-sdk-go-v2` |
| Argon2 密码验证 | `alexedwards/argon2id` |
| 配置 | 环境变量（与 Python 端共享 `.env`） |

### 与 FastAPI 的交互

```
FastAPI                          Storage Gateway
   │                                  │
   │  POST /api/v1/upload/session     │
   │  ──────────────────────────────→ │  创建上传会话
   │  ←────────────────────────────── │  返回 session_id + upload_url
   │                                  │
   │  (客户端直传到 Gateway)           │
   │                         PUT /upload/chunk/{session_id}
   │                                  │  写入存储后端
   │                                  │
   │  POST /internal/upload/complete  │
   │  ←────────────────────────────── │  回调通知上传完成
   │  更新 entry 元数据               │
```

- Gateway 通过 **内部 HTTP 回调** 通知 FastAPI 元数据变更
- FastAPI 通过 **Redis 队列** 下发迁移任务给 Gateway Worker
- 两者共享数据库，但职责分明：FastAPI 写元数据，Gateway 写字节流

---

## 实施阶段

### Phase 1：WebDAV 独立化

1. Go 服务实现 WebDAV 核心协议
2. 反向代理 `/dav/*` → Go
3. 从 FastAPI 移除 `routers/dav/` + `wsgidav` 依赖

### Phase 2：上传/下载迁移

1. Go 服务实现分片上传 + 文件下载
2. 反向代理 `/upload/*` `/download/*` → Go
3. FastAPI 端保留元数据 API，移除存储驱动直接操作

### Phase 3：迁移 Worker + 打包下载

1. Go Worker 从 Redis 消费迁移任务
2. FastAPI 的 `BackgroundTasks` 迁移改为 Redis 入队
3. 实现流式打包下载

### Phase 4：清理

1. 从 FastAPI 移除 `utils/storage/` 中的 S3 驱动（仅保留 Local 用于开发）
2. 移除 S3 相关 Python 依赖
3. 统一存储操作全部走 Gateway

---

## 待办：sqlmodel_ext 升级后迁移 validate_list

`sqlmodel_ext` 已新增 `SQLModelBase.validate_list()` classmethod，等 disknext 更新
sqlmodel_ext 依赖后，将以下 4 处列表推导替换为 `validate_list` 调用：

| 文件 | 行 | 当前写法 |
|------|-----|---------|
| `routers/api/v1/admin/theme/__init__.py` | 41 | `[ThemePresetResponse.model_validate(p, from_attributes=True) for p in presets]` |
| `routers/api/v1/site/__init__.py` | 60 | `[ThemePresetResponse.model_validate(p, from_attributes=True) for p in presets]` |
| `routers/api/v1/user/settings/__init__.py` | 452 | `[AuthnDetailResponse.model_validate(authn, from_attributes=True) for authn in authns]` |
| `routers/api/v1/admin/policy/__init__.py` | 45 | `[PolicySummary.model_validate(p, from_attributes=True) for p in result.items]` |

其余 8 处 for 循环因含 `update={}` 参数、循环内 `await`、条件过滤或元组构造，
无法使用 `validate_list`，保持现状。
