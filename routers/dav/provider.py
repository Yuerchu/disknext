"""
DiskNext WebDAV 存储 Provider

将 WsgiDAV 的文件操作映射到 DiskNext 的 Entry 模型。
所有异步数据库/文件操作通过 asyncio.run_coroutine_threadsafe() 桥接。
"""
import asyncio
import io
import mimetypes
from pathlib import Path
from typing import ClassVar
from uuid import UUID

from loguru import logger as l
from wsgidav.dav_error import (
    DAVError,
    HTTP_FORBIDDEN,
    HTTP_INSUFFICIENT_STORAGE,
    HTTP_NOT_FOUND,
)
from wsgidav.dav_provider import DAVCollection, DAVNonCollection, DAVProvider
from sqlmodel_ext import cond, rel

from utils.storage import create_storage_driver
from sqlmodels.database_connection import DatabaseManager
from sqlmodels.file import Entry, EntryType
from sqlmodels.physical_file import PhysicalFile
from sqlmodels.policy import Policy
from sqlmodels.user import User
from sqlmodels.webdav import WebDAV


class EventLoopRef:
    """持有主线程事件循环引用，供 WSGI 线程使用"""
    _loop: ClassVar[asyncio.AbstractEventLoop | None] = None

    @classmethod
    async def capture(cls) -> None:
        """在 async 上下文中调用，捕获当前事件循环"""
        cls._loop = asyncio.get_running_loop()

    @classmethod
    def get(cls) -> asyncio.AbstractEventLoop:
        if cls._loop is None:
            raise RuntimeError("事件循环尚未捕获，请先调用 EventLoopRef.capture()")
        return cls._loop


def _run_async(coro):  # type: ignore[no-untyped-def]
    """在 WSGI 线程中通过 run_coroutine_threadsafe 运行协程"""
    future = asyncio.run_coroutine_threadsafe(coro, EventLoopRef.get())
    return future.result()


def _get_session():  # type: ignore[no-untyped-def]
    """获取数据库会话上下文管理器"""
    return DatabaseManager._async_session_factory()


# ==================== 异步辅助函数 ====================

async def _get_webdav_account(webdav_id: UUID) -> WebDAV | None:
    """获取 WebDAV 账户"""
    async with _get_session() as session:
        return await WebDAV.get(session, WebDAV.id == webdav_id)


async def _get_object_by_path(user_id: UUID, path: str) -> Entry | None:
    """根据路径获取对象"""
    async with _get_session() as session:
        return await Entry.get_by_path(session, user_id, path)


async def _get_children(user_id: UUID, parent_id: UUID) -> list[Entry]:
    """获取目录子对象"""
    async with _get_session() as session:
        return await Entry.get_children(session, user_id, parent_id)


async def _get_object_by_id(file_id: UUID) -> Entry | None:
    """根据ID获取对象"""
    async with _get_session() as session:
        return await Entry.get(session, cond(Entry.id == file_id), load=rel(Entry.physical_file))


async def _get_user(user_id: UUID) -> User | None:
    """获取用户（含 group 关系）"""
    async with _get_session() as session:
        return await User.get(session, cond(User.id == user_id), load=rel(User.group))


async def _get_policy(policy_id: UUID) -> Policy | None:
    """获取存储策略"""
    async with _get_session() as session:
        return await Policy.get(session, Policy.id == policy_id)


async def _create_folder(
    name: str,
    parent_id: UUID,
    owner_id: UUID,
    policy_id: UUID,
) -> Entry:
    """创建目录对象"""
    async with _get_session() as session:
        obj = Entry(
            name=name,
            type=EntryType.FOLDER,
            size=0,
            parent_id=parent_id,
            owner_id=owner_id,
            policy_id=policy_id,
        )
        obj = await obj.save(session)
        return obj


async def _create_file(
    name: str,
    parent_id: UUID,
    owner_id: UUID,
    policy_id: UUID,
) -> Entry:
    """创建空文件对象"""
    async with _get_session() as session:
        obj = Entry(
            name=name,
            type=EntryType.FILE,
            size=0,
            parent_id=parent_id,
            owner_id=owner_id,
            policy_id=policy_id,
        )
        obj = await obj.save(session)
        return obj


async def _soft_delete_object(file_id: UUID) -> None:
    """软删除对象（移入回收站）"""
    async with _get_session() as session:
        obj = await Entry.get(session, Entry.id == file_id)
        if obj:
            await Entry.soft_delete_batch(session, [obj])


async def _finalize_upload(
    file_id: UUID,
    physical_path: str,
    size: int,
    owner_id: UUID,
    policy_id: UUID,
) -> None:
    """上传完成后更新对象元数据和物理文件记录"""
    async with _get_session() as session:
        # 获取存储路径（相对路径）
        policy = await Policy.get(session, Policy.id == policy_id)
        if not policy or not policy.server:
            raise DAVError(HTTP_NOT_FOUND, "存储策略不存在")

        base_path = Path(policy.server).resolve()
        full_path = Path(physical_path).resolve()
        storage_path = str(full_path.relative_to(base_path))

        # 创建 PhysicalFile 记录
        pf = PhysicalFile(
            storage_path=storage_path,
            size=size,
            policy_id=policy_id,
            reference_count=1,
        )
        pf = await pf.save(session)

        # 更新 File
        obj = await Entry.get(session, Entry.id == file_id)
        if obj:
            obj.sqlmodel_update({'size': size, 'physical_file_id': pf.id})
            obj = await obj.save(session)

        # 更新用户存储用量
        if size > 0:
            user = await User.get(session, User.id == owner_id)
            if user:
                await user.adjust_storage(session, size)


async def _move_object(
    file_id: UUID,
    new_parent_id: UUID,
    new_name: str,
) -> None:
    """移动/重命名对象"""
    async with _get_session() as session:
        obj = await Entry.get(session, Entry.id == file_id)
        if obj:
            obj.sqlmodel_update({'parent_id': new_parent_id, 'name': new_name})
            obj = await obj.save(session)


async def _copy_object_recursive(
    src_id: UUID,
    dst_parent_id: UUID,
    dst_name: str,
    owner_id: UUID,
) -> None:
    """递归复制对象"""
    async with _get_session() as session:
        src = await Entry.get(session, Entry.id == src_id)
        if not src:
            return
        await src.copy_recursive(session, dst_parent_id, owner_id)


# ==================== 辅助工具 ====================

def _get_environ_info(environ: dict[str, object]) -> tuple[UUID, int]:
    """从 environ 中提取认证信息"""
    user_id: UUID = environ["disknext.user_id"]  # type: ignore[assignment]
    webdav_id: int = environ["disknext.webdav_id"]  # type: ignore[assignment]
    return user_id, webdav_id


def _resolve_dav_path(account_root: str, dav_path: str) -> str:
    """
    将 DAV 相对路径映射到 DiskNext 绝对路径。

    :param account_root: 账户挂载根路径，如 "/" 或 "/docs"
    :param dav_path: DAV 请求路径，如 "/" 或 "/photos/cat.jpg"
    :return: DiskNext 内部路径，如 "/docs/photos/cat.jpg"
    """
    # 规范化根路径
    root = account_root.rstrip("/")
    if not root:
        root = ""

    # 规范化 DAV 路径
    if not dav_path or dav_path == "/":
        return root + "/" if root else "/"

    if not dav_path.startswith("/"):
        dav_path = "/" + dav_path

    full = root + dav_path
    return full if full else "/"


def _check_readonly(environ: dict[str, object]) -> None:
    """检查账户是否只读，只读则抛出 403"""
    account = environ.get("disknext.webdav_account")
    if account and getattr(account, 'readonly', False):
        raise DAVError(HTTP_FORBIDDEN, "WebDAV 账户为只读模式")


def _check_storage_quota(user: User, additional_bytes: int) -> None:
    """检查存储配额"""
    max_storage = user.group.max_storage
    if max_storage > 0 and user.storage + additional_bytes > max_storage:
        raise DAVError(HTTP_INSUFFICIENT_STORAGE, "存储空间不足")


class QuotaLimitedWriter(io.RawIOBase):
    """带配额限制的写入流包装器"""

    def __init__(self, stream: io.BufferedWriter, max_bytes: int) -> None:
        self._stream = stream
        self._max_bytes = max_bytes
        self._bytes_written = 0

    def writable(self) -> bool:
        return True

    def write(self, b: bytes | bytearray) -> int:
        if self._bytes_written + len(b) > self._max_bytes:
            raise DAVError(HTTP_INSUFFICIENT_STORAGE, "存储空间不足")
        written = self._stream.write(b)
        self._bytes_written += written
        return written

    def close(self) -> None:
        self._stream.close()
        super().close()

    @property
    def bytes_written(self) -> int:
        return self._bytes_written


# ==================== Provider ====================

class DiskNextDAVProvider(DAVProvider):
    """DiskNext WebDAV 存储 Provider"""

    def __init__(self) -> None:
        super().__init__()

    def get_resource_inst(
        self,
        path: str,
        environ: dict[str, object],
    ) -> 'DiskNextCollection | DiskNextFile | None':
        """
        将 WebDAV 路径映射到资源对象。

        首次调用时加载 WebDAV 账户信息并缓存到 environ。
        """
        user_id, webdav_id = _get_environ_info(environ)

        # 首次请求时加载账户信息
        if "disknext.webdav_account" not in environ:
            account = _run_async(_get_webdav_account(webdav_id))
            if not account:
                return None
            environ["disknext.webdav_account"] = account

        account: WebDAV = environ["disknext.webdav_account"]  # type: ignore[no-redef]
        disknext_path = _resolve_dav_path(account.root, path)

        obj = _run_async(_get_object_by_path(user_id, disknext_path))
        if not obj:
            return None

        if obj.type == EntryType.FOLDER:
            return DiskNextCollection(path, environ, obj, user_id, account)
        else:
            return DiskNextFile(path, environ, obj, user_id, account)

    def is_readonly(self) -> bool:
        """只读由账户级别控制，不在 provider 级别限制"""
        return False


# ==================== Collection（目录） ====================

class DiskNextCollection(DAVCollection):
    """DiskNext 目录资源"""

    def __init__(
        self,
        path: str,
        environ: dict[str, object],
        obj: Entry,
        user_id: UUID,
        account: WebDAV,
    ) -> None:
        super().__init__(path, environ)
        self._obj = obj
        self._user_id = user_id
        self._account = account

    def get_display_info(self) -> dict[str, str]:
        return {"type": "Directory"}

    def get_member_names(self) -> list[str]:
        """获取子对象名称列表"""
        children = _run_async(_get_children(self._user_id, self._obj.id))
        return [c.name for c in children]

    def get_member(self, name: str) -> 'DiskNextCollection | DiskNextFile | None':
        """获取指定名称的子资源"""
        member_path = self.path.rstrip("/") + "/" + name
        account_root = self._account.root
        disknext_path = _resolve_dav_path(account_root, member_path)

        obj = _run_async(_get_object_by_path(self._user_id, disknext_path))
        if not obj:
            return None

        if obj.type == EntryType.FOLDER:
            return DiskNextCollection(member_path, self.environ, obj, self._user_id, self._account)
        else:
            return DiskNextFile(member_path, self.environ, obj, self._user_id, self._account)

    def get_creation_date(self) -> float | None:
        if self._obj.created_at:
            return self._obj.created_at.timestamp()
        return None

    def get_last_modified(self) -> float | None:
        if self._obj.updated_at:
            return self._obj.updated_at.timestamp()
        return None

    def create_empty_resource(self, name: str) -> 'DiskNextFile':
        """创建空文件（PUT 操作的第一步）"""
        _check_readonly(self.environ)

        obj = _run_async(_create_file(
            name=name,
            parent_id=self._obj.id,
            owner_id=self._user_id,
            policy_id=self._obj.policy_id,
        ))

        member_path = self.path.rstrip("/") + "/" + name
        return DiskNextFile(member_path, self.environ, obj, self._user_id, self._account)

    def create_collection(self, name: str) -> 'DiskNextCollection':
        """创建子目录（MKCOL）"""
        _check_readonly(self.environ)

        obj = _run_async(_create_folder(
            name=name,
            parent_id=self._obj.id,
            owner_id=self._user_id,
            policy_id=self._obj.policy_id,
        ))

        member_path = self.path.rstrip("/") + "/" + name
        return DiskNextCollection(member_path, self.environ, obj, self._user_id, self._account)

    def delete(self) -> None:
        """软删除目录"""
        _check_readonly(self.environ)
        _run_async(_soft_delete_object(self._obj.id))

    def copy_move_single(self, dest_path: str, *, is_move: bool) -> bool:
        """复制或移动目录"""
        _check_readonly(self.environ)

        account_root = self._account.root
        dest_disknext = _resolve_dav_path(account_root, dest_path)

        # 解析目标父路径和新名称
        if "/" in dest_disknext.rstrip("/"):
            parent_path = dest_disknext.rsplit("/", 1)[0] or "/"
            new_name = dest_disknext.rsplit("/", 1)[1]
        else:
            parent_path = "/"
            new_name = dest_disknext.lstrip("/")

        dest_parent = _run_async(_get_object_by_path(self._user_id, parent_path))
        if not dest_parent:
            raise DAVError(HTTP_NOT_FOUND, "目标父目录不存在")

        if is_move:
            _run_async(_move_object(self._obj.id, dest_parent.id, new_name))
        else:
            _run_async(_copy_object_recursive(
                self._obj.id, dest_parent.id, new_name, self._user_id,
            ))

        return True

    def support_recursive_delete(self) -> bool:
        return True

    def support_recursive_move(self, dest_path: str) -> bool:
        return True


# ==================== NonCollection（文件） ====================

class DiskNextFile(DAVNonCollection):
    """DiskNext 文件资源"""

    def __init__(
        self,
        path: str,
        environ: dict[str, object],
        obj: Entry,
        user_id: UUID,
        account: WebDAV,
    ) -> None:
        super().__init__(path, environ)
        self._obj = obj
        self._user_id = user_id
        self._account = account
        self._write_path: str | None = None
        self._write_stream: io.BufferedWriter | QuotaLimitedWriter | None = None

    def get_content_length(self) -> int | None:
        return self._obj.size if self._obj.size else 0

    def get_content_type(self) -> str | None:
        # 尝试从文件名推断 MIME 类型
        mime, _ = mimetypes.guess_type(self._obj.name)
        return mime or "application/octet-stream"

    def get_creation_date(self) -> float | None:
        if self._obj.created_at:
            return self._obj.created_at.timestamp()
        return None

    def get_last_modified(self) -> float | None:
        if self._obj.updated_at:
            return self._obj.updated_at.timestamp()
        return None

    def get_display_info(self) -> dict[str, str]:
        return {"type": "File"}

    def get_content(self) -> io.BufferedReader | None:
        """
        返回文件内容的可读流。

        WsgiDAV 在线程中运行，可安全使用同步 open()。
        """
        obj_with_file = _run_async(_get_object_by_id(self._obj.id))
        if not obj_with_file or not obj_with_file.physical_file:
            return None

        pf = obj_with_file.physical_file
        policy = _run_async(_get_policy(obj_with_file.policy_id))
        if not policy or not policy.server:
            return None

        full_path = Path(policy.server).resolve() / pf.storage_path
        if not full_path.is_file():
            l.warning(f"WebDAV: 物理文件不存在: {full_path}")
            return None

        return open(full_path, "rb")  # noqa: SIM115

    def begin_write(
        self,
        *,
        content_type: str | None = None,
    ) -> io.BufferedWriter | QuotaLimitedWriter:
        """
        开始写入文件（PUT 操作）。

        返回一个可写的文件流，WsgiDAV 将向其中写入请求体数据。
        当用户有配额限制时，返回 QuotaLimitedWriter 在写入过程中实时检查配额。
        """
        _check_readonly(self.environ)

        # 检查配额
        remaining_quota: int = 0
        user = _run_async(_get_user(self._user_id))
        if user:
            max_storage = user.group.max_storage
            if max_storage > 0:
                remaining_quota = max_storage - user.storage
                if remaining_quota <= 0:
                    raise DAVError(HTTP_INSUFFICIENT_STORAGE, "存储空间不足")
                # Content-Length 预检（如果有的话）
                content_length = self.environ.get("CONTENT_LENGTH")
                if content_length and int(content_length) > remaining_quota:
                    raise DAVError(HTTP_INSUFFICIENT_STORAGE, "存储空间不足")

        # 获取策略以确定存储路径
        policy = _run_async(_get_policy(self._obj.policy_id))
        if not policy or not policy.server:
            raise DAVError(HTTP_NOT_FOUND, "存储策略不存在")

        driver = create_storage_driver(policy)
        dir_path, storage_name, full_path = _run_async(
            driver.generate_path(
                user_id=self._user_id,
                original_filename=self._obj.name,
            )
        )

        self._write_path = full_path
        raw_stream = open(full_path, "wb")  # noqa: SIM115

        # 有配额限制时使用包装流，实时检查写入量
        if remaining_quota > 0:
            self._write_stream = QuotaLimitedWriter(raw_stream, remaining_quota)
        else:
            self._write_stream = raw_stream

        return self._write_stream

    def end_write(self, *, with_errors: bool) -> None:
        """写入完成后的收尾工作"""
        if self._write_stream:
            self._write_stream.close()
            self._write_stream = None

        if with_errors:
            if self._write_path:
                file_path = Path(self._write_path)
                if file_path.exists():
                    file_path.unlink()
            return

        if not self._write_path:
            return

        # 获取文件大小
        file_path = Path(self._write_path)
        if not file_path.exists():
            return

        size = file_path.stat().st_size

        # 更新数据库记录
        _run_async(_finalize_upload(
            file_id=self._obj.id,
            physical_path=self._write_path,
            size=size,
            owner_id=self._user_id,
            policy_id=self._obj.policy_id,
        ))

        l.debug(f"WebDAV 文件写入完成: {self._obj.name}, size={size}")

    def delete(self) -> None:
        """软删除文件"""
        _check_readonly(self.environ)
        _run_async(_soft_delete_object(self._obj.id))

    def copy_move_single(self, dest_path: str, *, is_move: bool) -> bool:
        """复制或移动文件"""
        _check_readonly(self.environ)

        account_root = self._account.root
        dest_disknext = _resolve_dav_path(account_root, dest_path)

        # 解析目标父路径和新名称
        if "/" in dest_disknext.rstrip("/"):
            parent_path = dest_disknext.rsplit("/", 1)[0] or "/"
            new_name = dest_disknext.rsplit("/", 1)[1]
        else:
            parent_path = "/"
            new_name = dest_disknext.lstrip("/")

        dest_parent = _run_async(_get_object_by_path(self._user_id, parent_path))
        if not dest_parent:
            raise DAVError(HTTP_NOT_FOUND, "目标父目录不存在")

        if is_move:
            _run_async(_move_object(self._obj.id, dest_parent.id, new_name))
        else:
            _run_async(_copy_object_recursive(
                self._obj.id, dest_parent.id, new_name, self._user_id,
            ))

        return True

    def support_content_length(self) -> bool:
        return True

    def get_etag(self) -> str | None:
        """返回 ETag（基于ID和更新时间），WsgiDAV 会自动加双引号"""
        if self._obj.updated_at:
            return f"{self._obj.id}-{int(self._obj.updated_at.timestamp())}"
        return None

    def support_etag(self) -> bool:
        return True

    def support_ranges(self) -> bool:
        return True
