# 文本文件在线编辑 — 前端适配文档

## 概述

Monaco Editor 打开文本文件时，通过 GET 获取内容和哈希作为编辑基线；保存时用 jsdiff 计算 unified diff，仅发送差异部分，后端验证无并发冲突后应用 patch。

```
打开文件:  GET   /api/v1/file/content/{file_id}  →  { content, hash, size }
保存文件:  PATCH /api/v1/file/content/{file_id}  ←  { patch, base_hash }
                                                  →  { new_hash, new_size }
```

---

## 约定

| 项目 | 约定 |
|------|------|
| 编码 | 全程 UTF-8 |
| 换行符 | 后端 GET 时统一规范化为 `\n`，前端无需处理 `\r\n` |
| hash 算法 | SHA-256，hex 编码（64 字符），基于 UTF-8 bytes 计算 |
| diff 格式 | jsdiff `createPatch()` 输出的标准 unified diff |
| 空 diff | 前端自行判断，内容未变时不发请求 |

---

## GET /api/v1/file/content/{file_id}

获取文本文件内容。

### 请求

```
GET /api/v1/file/content/{file_id}
Authorization: Bearer <token>
```

### 响应 200

```json
{
  "content": "line1\nline2\nline3\n",
  "hash": "a1b2c3d4...（64字符 SHA-256 hex）",
  "size": 18
}
```

| 字段 | 类型 | 说明 |
|------|------|------|
| `content` | string | 文件文本内容，换行符已规范化为 `\n` |
| `hash` | string | 基于规范化内容 UTF-8 bytes 的 SHA-256 hex |
| `size` | number | 规范化后的字节大小 |

### 错误

| 状态码 | 说明 |
|--------|------|
| 400 | 文件不是有效的 UTF-8 文本（二进制文件） |
| 401 | 未认证 |
| 404 | 文件不存在 |

---

## PATCH /api/v1/file/content/{file_id}

增量保存文本文件。

### 请求

```
PATCH /api/v1/file/content/{file_id}
Authorization: Bearer <token>
Content-Type: application/json
```

```json
{
  "patch": "--- a\n+++ b\n@@ -1,3 +1,3 @@\n line1\n-line2\n+LINE2\n line3\n",
  "base_hash": "a1b2c3d4...（GET 返回的 hash）"
}
```

| 字段 | 类型 | 说明 |
|------|------|------|
| `patch` | string | jsdiff `createPatch()` 生成的 unified diff |
| `base_hash` | string | 编辑前 GET 返回的 `hash` 值 |

### 响应 200

```json
{
  "new_hash": "e5f6a7b8...（64字符）",
  "new_size": 18
}
```

保存成功后，前端应将 `new_hash` 作为新的 `base_hash`，用于下次保存。

### 错误

| 状态码 | 说明 | 前端处理 |
|--------|------|----------|
| 401 | 未认证 | — |
| 404 | 文件不存在 | — |
| 409 | `base_hash` 不匹配（并发冲突） | 提示用户刷新，重新加载内容 |
| 422 | patch 格式无效或应用失败 | 回退到全量保存或提示用户 |

---

## 前端实现参考

### 依赖

```bash
npm install jsdiff
```

### 计算 hash

```typescript
async function sha256(text: string): Promise<string> {
  const bytes = new TextEncoder().encode(text);
  const hashBuffer = await crypto.subtle.digest("SHA-256", bytes);
  const hashArray = Array.from(new Uint8Array(hashBuffer));
  return hashArray.map(b => b.toString(16).padStart(2, "0")).join("");
}
```

### 打开文件

```typescript
interface TextContent {
  content: string;
  hash: string;
  size: number;
}

async function openFile(fileId: string): Promise<TextContent> {
  const resp = await fetch(`/api/v1/file/content/${fileId}`, {
    headers: { Authorization: `Bearer ${token}` },
  });

  if (!resp.ok) {
    if (resp.status === 400) throw new Error("该文件不是文本文件");
    throw new Error("获取文件内容失败");
  }

  return resp.json();
}
```

### 保存文件

```typescript
import { createPatch } from "diff";

interface PatchResult {
  new_hash: string;
  new_size: number;
}

async function saveFile(
  fileId: string,
  originalContent: string,
  currentContent: string,
  baseHash: string,
): Promise<PatchResult | null> {
  // 内容未变，不发请求
  if (originalContent === currentContent) return null;

  const patch = createPatch("file", originalContent, currentContent);

  const resp = await fetch(`/api/v1/file/content/${fileId}`, {
    method: "PATCH",
    headers: {
      Authorization: `Bearer ${token}`,
      "Content-Type": "application/json",
    },
    body: JSON.stringify({ patch, base_hash: baseHash }),
  });

  if (resp.status === 409) {
    // 并发冲突，需要用户决策
    throw new Error("CONFLICT");
  }

  if (!resp.ok) throw new Error("保存失败");

  return resp.json();
}
```

### 完整编辑流程

```typescript
// 1. 打开
const file = await openFile(fileId);
let baseContent = file.content;
let baseHash = file.hash;

// 2. 用户在 Monaco 中编辑...
editor.setValue(baseContent);

// 3. 保存（Ctrl+S）
const currentContent = editor.getValue();
const result = await saveFile(fileId, baseContent, currentContent, baseHash);

if (result) {
  // 更新基线
  baseContent = currentContent;
  baseHash = result.new_hash;
}
```

### 冲突处理建议

当 PATCH 返回 409 时，说明文件已被其他会话修改：

```typescript
try {
  await saveFile(fileId, baseContent, currentContent, baseHash);
} catch (e) {
  if (e.message === "CONFLICT") {
    // 方案 A：提示用户，提供"覆盖"和"放弃"选项
    // 方案 B：重新 GET 最新内容，展示 diff 让用户合并
    const latest = await openFile(fileId);
    // 展示合并 UI...
  }
}
```

---

## hash 一致性验证

前端可以在 GET 后本地验证 hash，确保传输无误：

```typescript
const file = await openFile(fileId);
const localHash = await sha256(file.content);
console.assert(localHash === file.hash, "hash 不一致，内容可能损坏");
```
