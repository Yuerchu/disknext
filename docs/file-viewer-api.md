# 文件预览应用选择器 — 前端适配文档

## 概述

文件预览系统类似 Android 的"使用什么应用打开"机制：用户点击文件时，前端根据扩展名查询可用查看器列表，展示选择弹窗，用户可选"仅此一次"或"始终使用"。

### 应用类型

| type | 说明 | 前端处理方式 |
|------|------|-------------|
| `builtin` | 前端内置组件 | 根据 `app_key` 路由到内置组件（如 `pdfjs`、`monaco`） |
| `iframe` | iframe 内嵌 | 将 `iframe_url_template` 中的 `{file_url}` 替换为文件下载 URL，嵌入 iframe |
| `wopi` | WOPI 协议 | 调用 `/file/{id}/wopi_session` 获取 `editor_url`，嵌入 iframe |

### 内置 app_key 映射

前端需要为以下 `app_key` 实现对应的内置预览组件：

| app_key | 组件 | 说明 |
|---------|------|------|
| `pdfjs` | PDF.js 阅读器 | pdf |
| `monaco` | Monaco Editor | txt, md, json, py, js, ts, html, css, ... |
| `markdown` | Markdown 渲染器 | md, markdown, mdx |
| `image_viewer` | 图片查看器 | jpg, png, gif, webp, svg, ... |
| `video_player` | HTML5 Video | mp4, webm, ogg, mov, mkv, m3u8 |
| `audio_player` | HTML5 Audio | mp3, wav, flac, aac, m4a, opus |

> `office_viewer`（iframe）、`collabora`（wopi）、`onlyoffice`（wopi）默认禁用，需管理员在后台启用和配置。

---

## 文件下载 URL 与 iframe 预览

### 现有下载流程（两步式）

```
步骤1: POST /api/v1/file/download/{file_id}    →  { access_token, expires_in }
步骤2: GET  /api/v1/file/download/{access_token} →  文件二进制流
```

- 步骤 1 需要 JWT 认证，返回一个下载令牌（有效期 1 小时）
- 步骤 2 **不需要认证**，用令牌直接下载，**令牌为一次性**，下载后失效

### 各类型查看器获取文件内容的方式

| type | 获取文件方式 | 说明 |
|------|-------------|------|
| `builtin` | 前端自行获取 | 前端用 JS 调用下载接口拿到 Blob/ArrayBuffer，传给内置组件渲染 |
| `iframe` | 需要公开可访问的 URL | 第三方服务（如 Office Online）会**从服务端拉取文件** |
| `wopi` | WOPI 协议自动处理 | 编辑器通过 `/wopi/files/{id}/contents` 获取，前端只需嵌入 `editor_url` |

### builtin 类型 — 前端自行获取

内置组件（pdfjs、monaco 等）运行在前端，直接用 JS 获取文件内容即可：

```typescript
// 方式 A：用下载令牌拼 URL（适用于 PDF.js 等需要 URL 的组件）
const { access_token } = await api.post(`/file/download/${fileId}`)
const fileUrl = `${baseUrl}/api/v1/file/download/${access_token}`
// 传给 PDF.js: pdfjsLib.getDocument(fileUrl)

// 方式 B：用 fetch + Authorization 头获取 Blob（适用于需要 ArrayBuffer 的组件）
const { access_token } = await api.post(`/file/download/${fileId}`)
const blob = await fetch(`${baseUrl}/api/v1/file/download/${access_token}`).then(r => r.blob())
// 传给 Monaco: monaco.editor.create(el, { value: await blob.text() })
```

### iframe 类型 — `{file_url}` 替换规则

`iframe_url_template` 中的 `{file_url}` 需要替换为一个**外部可访问的文件直链**。

**问题**：当前下载令牌是一次性的，而 Office Online 等服务可能多次请求该 URL。

**当前可行方案**：

```typescript
// 1. 创建下载令牌
const { access_token } = await api.post(`/file/download/${fileId}`)

// 2. 拼出完整的文件 URL（必须是公网可达的地址）
const fileUrl = `${siteURL}/api/v1/file/download/${access_token}`

// 3. 替换模板
const iframeSrc = viewer.iframe_url_template.replace(
  '{file_url}',
  encodeURIComponent(fileUrl)
)

// 4. 嵌入 iframe
// <iframe src={iframeSrc} />
```

> **已知限制**：下载令牌为一次性使用。如果第三方服务多次拉取文件（如 Office Online 可能重试），
> 第二次请求会 404。后续版本将实现 `/file/get/{id}/{name}` 外链端点（多次可用），届时
> iframe 应改用外链 URL。目前建议：
>
> 1. **优先使用 WOPI 类型**（Collabora/OnlyOffice），不存在此限制
> 2. Office Online 预览在**文件较小**时通常只拉取一次，大多数场景可用
> 3. 如需稳定方案，可等待外链端点实现后再启用 iframe 类型应用

### wopi 类型 — 无需关心文件 URL

WOPI 类型的查看器完全由后端处理文件传输，前端只需：

```typescript
// 1. 创建 WOPI 会话
const session = await api.post(`/file/${fileId}/wopi_session`)

// 2. 直接嵌入编辑器
// <iframe src={session.editor_url} />
```

编辑器（Collabora/OnlyOffice）会通过 WOPI 协议自动从 `/wopi/files/{id}/contents` 获取文件内容，使用 `access_token` 认证，前端无需干预。

---

## 用户端 API

### 1. 查询可用查看器

用户点击文件时调用，获取该扩展名的可用查看器列表。

```
GET /api/v1/file/viewers?ext={extension}
Authorization: Bearer {token}
```

**Query 参数**

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| ext | string | 是 | 文件扩展名，最长 20 字符。支持带点号（`.pdf`）、大写（`PDF`），后端会自动规范化 |

**响应 200**

```json
{
  "viewers": [
    {
      "id": "550e8400-e29b-41d4-a716-446655440000",
      "name": "PDF 阅读器",
      "app_key": "pdfjs",
      "type": "builtin",
      "icon": "file-pdf",
      "description": "基于 pdf.js 的 PDF 在线阅读器",
      "iframe_url_template": null,
      "wopi_editor_url_template": null
    }
  ],
  "default_viewer_id": null
}
```

**字段说明**

| 字段 | 类型 | 说明 |
|------|------|------|
| viewers | FileAppSummary[] | 可用查看器列表，已按优先级排序 |
| default_viewer_id | string \| null | 用户设置的"始终使用"查看器 UUID，未设置则为 null |

**FileAppSummary**

| 字段 | 类型 | 说明 |
|------|------|------|
| id | UUID | 应用 UUID |
| name | string | 应用显示名称 |
| app_key | string | 应用唯一标识，前端路由用 |
| type | `"builtin"` \| `"iframe"` \| `"wopi"` | 应用类型 |
| icon | string \| null | 图标名称（可映射到 icon library） |
| description | string \| null | 应用描述 |
| iframe_url_template | string \| null | iframe 类型专用，URL 模板含 `{file_url}` 占位符 |
| wopi_editor_url_template | string \| null | wopi 类型专用，编辑器 URL 模板 |

---

### 2. 设置默认查看器（"始终使用"）

用户在选择弹窗中勾选"始终使用此应用"时调用。

```
PUT /api/v1/user/settings/file_viewers/default
Authorization: Bearer {token}
Content-Type: application/json
```

**请求体**

```json
{
  "extension": "pdf",
  "app_id": "550e8400-e29b-41d4-a716-446655440000"
}
```

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| extension | string | 是 | 文件扩展名（小写，无点号） |
| app_id | UUID | 是 | 选择的查看器应用 UUID |

**响应 200**

```json
{
  "id": "660e8400-e29b-41d4-a716-446655440001",
  "extension": "pdf",
  "app": {
    "id": "550e8400-e29b-41d4-a716-446655440000",
    "name": "PDF 阅读器",
    "app_key": "pdfjs",
    "type": "builtin",
    "icon": "file-pdf",
    "description": "基于 pdf.js 的 PDF 在线阅读器",
    "iframe_url_template": null,
    "wopi_editor_url_template": null
  }
}
```

**错误码**

| 状态码 | 说明 |
|--------|------|
| 400 | 该应用不支持此扩展名 |
| 404 | 应用不存在 |

> 同一扩展名只允许一个默认值。重复 PUT 同一 extension 会更新（upsert），不会冲突。

---

### 3. 列出所有默认查看器设置

用于用户设置页展示"已设为始终使用"的列表。

```
GET /api/v1/user/settings/file_viewers/defaults
Authorization: Bearer {token}
```

**响应 200**

```json
[
  {
    "id": "660e8400-e29b-41d4-a716-446655440001",
    "extension": "pdf",
    "app": {
      "id": "550e8400-e29b-41d4-a716-446655440000",
      "name": "PDF 阅读器",
      "app_key": "pdfjs",
      "type": "builtin",
      "icon": "file-pdf",
      "description": null,
      "iframe_url_template": null,
      "wopi_editor_url_template": null
    }
  }
]
```

---

### 4. 撤销默认查看器设置

用户在设置页点击"取消始终使用"时调用。

```
DELETE /api/v1/user/settings/file_viewers/default/{id}
Authorization: Bearer {token}
```

**响应** 204 No Content

**错误码**

| 状态码 | 说明 |
|--------|------|
| 404 | 记录不存在或不属于当前用户 |

---

### 5. 创建 WOPI 会话

打开 WOPI 类型应用（如 Collabora、OnlyOffice）时调用。

```
POST /api/v1/file/{file_id}/wopi_session
Authorization: Bearer {token}
```

**响应 200**

```json
{
  "wopi_src": "http://localhost:8000/wopi/files/770e8400-e29b-41d4-a716-446655440002",
  "access_token": "eyJhbGciOiJIUzI1NiIs...",
  "access_token_ttl": 1739577600000,
  "editor_url": "http://collabora:9980/loleaflet/dist/loleaflet.html?WOPISrc=...&access_token=...&access_token_ttl=..."
}
```

| 字段 | 类型 | 说明 |
|------|------|------|
| wopi_src | string | WOPI 源 URL（传给编辑器） |
| access_token | string | WOPI 访问令牌 |
| access_token_ttl | int | 令牌过期毫秒时间戳 |
| editor_url | string | 完整的编辑器 URL，**直接嵌入 iframe 即可** |

**错误码**

| 状态码 | 说明 |
|--------|------|
| 400 | 文件无扩展名 / WOPI 应用未配置编辑器 URL |
| 403 | 用户组无权限 |
| 404 | 文件不存在 / 无可用 WOPI 查看器 |

---

## 前端交互流程

### 打开文件预览

```
用户点击文件
    │
    ▼
GET /file/viewers?ext={扩展名}
    │
    ├── viewers 为空 → 提示"暂无可用的预览方式"
    │
    ├── default_viewer_id 不为空 → 直接用对应 viewer 打开（跳过选择弹窗）
    │
    └── viewers.length == 1 → 直接用唯一 viewer 打开（可选策略）
    │
    └── viewers.length > 1 → 展示选择弹窗
                │
                ├── 用户选择 + 不勾选"始终使用" → 仅此一次打开
                │
                └── 用户选择 + 勾选"始终使用" → PUT /user/settings/file_viewers/default
                                                     │
                                                     └── 然后打开
```

### 根据 type 打开查看器

```
获取到 viewer 对象
    │
    ├── type == "builtin"
    │       └── 根据 app_key 路由到内置组件
    │           switch(app_key):
    │             "pdfjs"        → <PdfViewer />
    │             "monaco"       → <CodeEditor />
    │             "markdown"     → <MarkdownPreview />
    │             "image_viewer" → <ImageViewer />
    │             "video_player" → <VideoPlayer />
    │             "audio_player" → <AudioPlayer />
    │
    │           获取文件内容：
    │             POST /file/download/{file_id} → { access_token }
    │             fileUrl = `${siteURL}/api/v1/file/download/${access_token}`
    │             → 传 URL 或 fetch Blob 给内置组件
    │
    ├── type == "iframe"
    │       └── 1. POST /file/download/{file_id} → { access_token }
    │           2. fileUrl = `${siteURL}/api/v1/file/download/${access_token}`
    │           3. iframeSrc = viewer.iframe_url_template
    │                .replace("{file_url}", encodeURIComponent(fileUrl))
    │           4. <iframe src={iframeSrc} />
    │
    └── type == "wopi"
            └── 1. POST /file/{file_id}/wopi_session → { editor_url }
                2. <iframe src={editor_url} />
                   （编辑器自动通过 WOPI 协议获取文件，前端无需处理）
```

---

## 管理员 API

所有管理端点需要管理员身份（JWT 中 group.admin == true）。

### 1. 列出所有文件应用

```
GET /api/v1/admin/file_app/?page=1&page_size=20
Authorization: Bearer {admin_token}
```

**响应 200**

```json
{
  "apps": [
    {
      "id": "...",
      "name": "PDF 阅读器",
      "app_key": "pdfjs",
      "type": "builtin",
      "icon": "file-pdf",
      "description": "...",
      "is_enabled": true,
      "is_restricted": false,
      "iframe_url_template": null,
      "wopi_discovery_url": null,
      "wopi_editor_url_template": null,
      "extensions": ["pdf"],
      "allowed_group_ids": []
    }
  ],
  "total": 9
}
```

### 2. 创建文件应用

```
POST /api/v1/admin/file_app/
Authorization: Bearer {admin_token}
Content-Type: application/json
```

```json
{
  "name": "自定义查看器",
  "app_key": "my_viewer",
  "type": "iframe",
  "description": "自定义 iframe 查看器",
  "is_enabled": true,
  "is_restricted": false,
  "iframe_url_template": "https://example.com/view?url={file_url}",
  "extensions": ["pdf", "docx"],
  "allowed_group_ids": []
}
```

**响应** 201 — 返回 FileAppResponse（同列表中的单项）

**错误码**: 409 — app_key 已存在

### 3. 获取应用详情

```
GET /api/v1/admin/file_app/{id}
```

**响应** 200 — FileAppResponse

### 4. 更新应用

```
PATCH /api/v1/admin/file_app/{id}
```

只传需要更新的字段：

```json
{
  "name": "新名称",
  "is_enabled": false
}
```

**响应** 200 — FileAppResponse

### 5. 删除应用

```
DELETE /api/v1/admin/file_app/{id}
```

**响应** 204 No Content（级联删除扩展名关联、用户偏好、用户组关联）

### 6. 全量替换扩展名列表

```
PUT /api/v1/admin/file_app/{id}/extensions
```

```json
{
  "extensions": ["doc", "docx", "odt"]
}
```

**响应** 200 — FileAppResponse

### 7. 全量替换允许的用户组

```
PUT /api/v1/admin/file_app/{id}/groups
```

```json
{
  "group_ids": ["uuid-1", "uuid-2"]
}
```

**响应** 200 — FileAppResponse

> `is_restricted` 为 `true` 时，只有 `allowed_group_ids` 中的用户组成员能看到此应用。`is_restricted` 为 `false` 时所有用户可见，`allowed_group_ids` 不生效。

---

## TypeScript 类型参考

```typescript
type FileAppType = 'builtin' | 'iframe' | 'wopi'

interface FileAppSummary {
  id: string
  name: string
  app_key: string
  type: FileAppType
  icon: string | null
  description: string | null
  iframe_url_template: string | null
  wopi_editor_url_template: string | null
}

interface FileViewersResponse {
  viewers: FileAppSummary[]
  default_viewer_id: string | null
}

interface SetDefaultViewerRequest {
  extension: string
  app_id: string
}

interface UserFileAppDefaultResponse {
  id: string
  extension: string
  app: FileAppSummary
}

interface WopiSessionResponse {
  wopi_src: string
  access_token: string
  access_token_ttl: number
  editor_url: string
}

// ========== 管理员类型 ==========

interface FileAppResponse {
  id: string
  name: string
  app_key: string
  type: FileAppType
  icon: string | null
  description: string | null
  is_enabled: boolean
  is_restricted: boolean
  iframe_url_template: string | null
  wopi_discovery_url: string | null
  wopi_editor_url_template: string | null
  extensions: string[]
  allowed_group_ids: string[]
}

interface FileAppListResponse {
  apps: FileAppResponse[]
  total: number
}

interface FileAppCreateRequest {
  name: string
  app_key: string
  type: FileAppType
  icon?: string
  description?: string
  is_enabled?: boolean       // default: true
  is_restricted?: boolean    // default: false
  iframe_url_template?: string
  wopi_discovery_url?: string
  wopi_editor_url_template?: string
  extensions?: string[]      // default: []
  allowed_group_ids?: string[] // default: []
}

interface FileAppUpdateRequest {
  name?: string
  app_key?: string
  type?: FileAppType
  icon?: string
  description?: string
  is_enabled?: boolean
  is_restricted?: boolean
  iframe_url_template?: string
  wopi_discovery_url?: string
  wopi_editor_url_template?: string
}
```
