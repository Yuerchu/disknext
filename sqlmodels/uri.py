from enum import StrEnum
from typing import Any, Self

from yarl import URL

from sqlmodel_ext import SQLModelBase


class FileSystemNamespace(StrEnum):
    """文件系统命名空间"""

    MY = "my"
    """用户个人空间"""

    SHARE = "share"
    """分享空间"""

    TRASH = "trash"
    """回收站"""


class DiskNextURI(SQLModelBase):
    """
    DiskNext 文件 URI

    URI 格式: disknext://[fs_id[:password]@]namespace[/path][?query]

    fs_id 可省略：
    - my/trash 命名空间省略时默认当前用户
    - share 命名空间必须提供 fs_id（Share.code）

    路径中的 URI 保留字符（``?``, ``#``, ``@`` 等）由 yarl 自动
    percent-encode/decode，``path`` 字段始终存储解码后的人类可读路径。
    文件名的合法性校验（``/``, ``\\`` 等）由 Entry 模型的数据库约束负责。
    """

    fs_id: str | None = None
    """文件系统标识符，可省略"""

    namespace: FileSystemNamespace
    """命名空间"""

    path: str = "/"
    """路径（已解码，人类可读）"""

    password: str | None = None
    """访问密码（用于有密码的分享）"""

    query: dict[str, str] | None = None
    """查询参数"""

    @staticmethod
    def _normalize_path(path: str) -> str:
        """规范化路径，保证至少为根路径且以 / 开头"""
        if not path:
            return "/"
        if not path.startswith("/"):
            return "/" + path
        return path

    def _to_url(self) -> URL:
        """构造 yarl.URL 实例"""
        kwargs: dict[str, Any] = {
            'scheme': "disknext",
            'host': self.namespace.value,
            'path': self.path,
        }
        if self.fs_id is not None:
            kwargs['user'] = self.fs_id
        if self.password is not None:
            kwargs['password'] = self.password
        if self.query:
            kwargs['query'] = self.query
        return URL.build(**kwargs)

    @property
    def path_parts(self) -> list[str]:
        """路径分割为列表（过滤空串）"""
        return [part for part in self.path.split("/") if part]

    @property
    def is_root(self) -> bool:
        """是否指向根目录"""
        return self.path.strip("/") == ""

    def id(self, default_id: str | None = None) -> str | None:
        """
        获取 fs_id，省略时返回 default_id

        :param default_id: 默认值，通常为当前用户 ID
        :return: fs_id 或 default_id
        """
        return self.fs_id if self.fs_id else default_id

    @classmethod
    def parse(cls, uri: str) -> Self:
        """
        解析 URI 字符串

        :param uri: URI 字符串，如 "disknext://my/docs/readme.md"
        :return: DiskNextURI 实例
        :raises ValueError: URI 格式无效
        """
        url = URL(uri)

        if url.scheme != "disknext":
            raise ValueError(f"URI 必须以 disknext:// 开头: {uri}")

        raw_namespace: str | None = url.host
        if not raw_namespace:
            raise ValueError(f"URI 缺少命名空间: {uri}")

        namespace: FileSystemNamespace
        try:
            namespace = FileSystemNamespace(raw_namespace)
        except ValueError as exc:
            valid_namespaces: list[str] = [item.value for item in FileSystemNamespace]
            raise ValueError(
                f"无效的命名空间 '{raw_namespace}'，有效值: {valid_namespaces}"
            ) from exc

        return cls(
            fs_id=url.user,
            namespace=namespace,
            path=cls._normalize_path(url.path),
            password=url.password,
            query=dict(url.query) if url.query_string else None,
        )

    @classmethod
    def build(
        cls,
        namespace: FileSystemNamespace,
        path: str = "/",
        fs_id: str | None = None,
        password: str | None = None,
    ) -> Self:
        """
        构建 URI 实例

        :param namespace: 命名空间
        :param path: 路径
        :param fs_id: 文件系统标识符
        :param password: 访问密码
        :return: DiskNextURI 实例
        """
        return cls(
            fs_id=fs_id,
            namespace=namespace,
            path=cls._normalize_path(path),
            password=password,
        )

    def to_string(self) -> str:
        """
        序列化为 URI 字符串

        :return: URI 字符串，如 "disknext://my/docs/readme.md"
        """
        return str(self._to_url())

    def join(self, *elements: str) -> Self:
        """
        拼接路径元素，返回新 URI

        :param elements: 路径元素
        :return: 新的 DiskNextURI 实例
        """
        path_parts: list[str] = self.path_parts.copy()
        for element in elements:
            normalized_element: str = element.strip("/")
            if normalized_element:
                path_parts.append(normalized_element)

        joined_path: str = "/" + "/".join(path_parts) if path_parts else "/"
        return self.__class__(
            fs_id=self.fs_id,
            namespace=self.namespace,
            path=joined_path,
            password=self.password,
            query=self.query.copy() if self.query else None,
        )

    def dir_uri(self) -> Self:
        """
        返回父目录的 URI

        :return: 父目录的 DiskNextURI 实例
        """
        parts: list[str] = self.path_parts
        if not parts:
            return self.root()

        parent_parts: list[str] = parts[:-1]
        parent_path: str = "/" + "/".join(parent_parts) if parent_parts else "/"
        if parent_path != "/":
            parent_path += "/"

        return self.__class__(
            fs_id=self.fs_id,
            namespace=self.namespace,
            path=parent_path,
            password=self.password,
        )

    def root(self) -> Self:
        """
        返回根目录 URI，保留 namespace 和 fs_id

        :return: 根目录的 DiskNextURI 实例
        """
        return self.__class__(
            fs_id=self.fs_id,
            namespace=self.namespace,
            path="/",
            password=self.password,
        )

    def name(self) -> str:
        """
        返回路径最后一段

        :return: 文件名或目录名，根目录返回空字符串
        """
        parts: list[str] = self.path_parts
        return parts[-1] if parts else ""

    def __str__(self) -> str:
        return self.to_string()

    def __repr__(self) -> str:
        return f"DiskNextURI({self.to_string()!r})"
