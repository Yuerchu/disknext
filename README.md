<h1 align="center">
  <br>
  DiskNext Server
  <br>
</h1>

<h4 align="center">支持多家云存储的公私兼备的云服务系统后端</h4>

<p align="center">
  <img src="https://img.shields.io/badge/Python-3.13+-blue?logo=python" alt="Python">
  <img src="https://img.shields.io/badge/FastAPI-0.122+-green?logo=fastapi" alt="FastAPI">
  <img src="https://img.shields.io/badge/SQLModel-0.0.27+-orange" alt="SQLModel">
  <img src="https://img.shields.io/badge/License-GPLv3-red" alt="License">
  <img src="https://img.shields.io/badge/Status-OMEGA-yellow" alt="Status">
</p>

---

本项目旨在集百家之长（Cloudreve + Alist/OpenList + FnOS + KodBox），打造一个功能强大、安全可靠的云存储解决方案。

> **注意**：目前正处于 `OMEGA` 实验阶段，比 `Alpha` 版还更早期，仅供测试和开发。

## 特性

### 存储能力

- **多存储策略**：支持本地存储、S3 兼容 API、阿里云 OSS、OneDrive 等多种存储后端
- **远程节点**：可对接从节点分担存储和下载任务
- **WebDAV 兼容**：提供标准 WebDAV 接口，支持第三方客户端访问

### 文件管理

- **统一对象模型**：文件和目录采用统一的 Object 模型管理
- **在线压缩/解压**：支持批量打包下载
- **离线下载**：内置离线下载服务，也可对接 Aria2/qBittorrent

### 用户与权限

- **多用户系统**：支持用户注册、登录、个人设置
- **用户组管理**：灵活的分级权限控制
- **存储配额**：可为用户组设置存储空间限制

### 安全能力

- **JWT 令牌认证**：基于 OAuth2.1 规范的安全认证
- **两步验证 (2FA)**：支持 TOTP 两步验证
- **WebAuthn**：支持 Passkey 无密码登录
- **OAuth 登录**：支持 QQ、GitHub 等第三方登录

### 分享功能

- **分享链接管理**：可设置密码、过期时间
- **分享页展示**：支持 README 渲染、媒体元数据展示

### 增值服务

- **积分系统**：支持用户积分管理
- **兑换码**：支持兑换码功能
- **容量包**：可购买额外存储空间

## 技术栈

### 后端

| 技术 | 说明 |
|------|------|
| [Python 3.13+](https://www.python.org/) | 编程语言 |
| [FastAPI](https://fastapi.tiangolo.com/) | 高性能异步 Web 框架 |
| [SQLModel](https://sqlmodel.tiangolo.com/) | 类型安全的 ORM（SQLAlchemy + Pydantic） |
| [aiohttp](https://docs.aiohttp.org/) | 异步 HTTP 客户端 |
| [aiosqlite](https://aiosqlite.omnilib.dev/) | 异步 SQLite 驱动 |
| [Loguru](https://loguru.readthedocs.io/) | 现代化日志库 |
| [PyJWT](https://pyjwt.readthedocs.io/) | JWT 令牌处理 |
| [WebAuthn](https://pypi.org/project/webauthn/) | Passkey 认证支持 |
| [Argon2](https://argon2-cffi.readthedocs.io/) | 安全密码哈希 |
| [pytest](https://pytest.org/) | 测试框架 |

## 项目结构

```
Server/
├── main.py              # 应用入口
├── models/              # 数据模型
│   ├── base/            # 基类定义 (SQLModelBase, TableBase)
│   ├── user.py          # 用户模型
│   ├── group.py         # 用户组模型
│   ├── object.py        # 文件/目录统一模型
│   ├── policy.py        # 存储策略模型
│   ├── share.py         # 分享模型
│   └── ...
├── routers/             # API 路由
│   └── api/v1/          # v1 版本 API
│       ├── user/        # 用户相关接口
│       ├── directory/   # 目录相关接口
│       ├── file/        # 文件相关接口
│       ├── admin/       # 管理员接口
│       └── ...
├── service/             # 业务服务层
│   ├── user/            # 用户服务
│   ├── captcha/         # 验证码服务
│   └── oauth/           # OAuth 服务
├── middleware/          # 中间件
│   ├── auth.py          # 认证中间件
│   └── dependencies.py  # 依赖注入
├── utils/               # 工具函数
│   ├── JWT/             # JWT 处理
│   ├── password/        # 密码处理
│   ├── conf/            # 配置管理
│   └── lifespan/        # 生命周期管理
└── tests/               # 测试用例
    ├── unit/            # 单元测试
    ├── integration/     # 集成测试
    └── fixtures/        # 测试夹具
```

## API 概览

| 模块 | 前缀 | 说明 |
|------|------|------|
| 站点 | `/api/v1/site` | 站点配置和公开信息 |
| 用户 | `/api/v1/user` | 用户注册、登录、设置 |
| 目录 | `/api/v1/directory` | 目录浏览和管理 |
| 文件 | `/api/v1/file` | 文件上传、下载、管理 |
| 对象 | `/api/v1/object` | 文件和目录的通用操作 |
| 分享 | `/api/v1/share` | 分享链接管理 |
| 下载 | `/api/v1/download` | 离线下载管理 |
| 标签 | `/api/v1/tag` | 用户标签管理 |
| WebDAV | `/api/v1/webdav` | WebDAV 账号管理 |
| 增值服务 | `/api/v1/vas` | 积分、兑换码等 |
| 回调 | `/api/v1/callback` | 第三方回调接口 |
| 从节点 | `/api/v1/slave` | 从节点通信接口 |
| 管理员 | `/api/v1/admin/*` | 后台管理接口 |

## 快速开始

### 环境要求

- Python 3.13 或更高版本
- uv (推荐) 或 pip

### 安装

```bash
# 克隆项目
git clone https://github.com/DiskNext/Server.git
cd Server

# 使用 uv 安装依赖
uv sync
```

### 配置

创建 `.env` 文件配置环境变量：

```env
# 调试模式
DEBUG=false

# 数据库连接（默认使用 SQLite）
DATABASE_URL=sqlite+aiosqlite:///disknext.db
```

### 启动

```bash
# 开发模式
fastapi dev

# 生产模式
fastapi run
```

访问 http://localhost:8000/docs 查看 API 文档。

## 测试

```bash
# 运行所有测试
pytest

# 运行单元测试
pytest tests/unit

# 运行集成测试
pytest tests/integration

# 生成覆盖率报告
pytest --cov
```

## 开发规范

详细的开发规范请参阅 [CLAUDE.md](CLAUDE.md)，主要包括：

- 类型安全与显式优于隐式
- 异步优先，IO 绝不阻塞
- 单一真相来源原则
- 目录结构即 API 结构
- SQLModel 使用规范

## 路线图

查看 [ROADMAP.md](ROADMAP.md) 了解项目开发计划。

## 贡献

欢迎提交 Issue 和 Pull Request！

## 许可证

本项目采用 [GPL v3](https://opensource.org/license/gpl-3.0) 许可证。

---

> 你也可以考虑付费支持我们的发展 -> `DiskNext Pro`
