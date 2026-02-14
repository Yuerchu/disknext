
from enum import StrEnum
from urllib.parse import urlparse, parse_qs, urlencode, quote, unquote

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
    """

    fs_id: str | None = None
    """文件系统标识符，可省略"""

    namespace: FileSystemNamespace
    """命名空间"""

    path: str = "/"
    """路径"""

    password: str | None = None
    """访问密码（用于有密码的分享）"""

    query: dict[str, str] | None = None
    """查询参数"""

    # === 属性 ===

    @property
    def path_parts(self) -> list[str]:
        """路径分割为列表（过滤空串）"""
        return [p for p in self.path.split("/") if p]

    @property
    def is_root(self) -> bool:
        """是否指向根目录"""
        return self.path.strip("/") == ""

    # === 核心方法 ===

    def id(self, default_id: str | None = None) -> str | None:
        """
        获取 fs_id，省略时返回 default_id

        参考 Cloudreve URI.ID(defaultUid) 方法

        :param default_id: 默认值（通常为当前用户 ID）
        :return: fs_id 或 default_id
        """
        return self.fs_id if self.fs_id else default_id

    # === 类方法 ===

    @classmethod
    def parse(cls, uri: str) -> "DiskNextURI":
        """
        解析 URI 字符串

        实现方式：替换 disknext:// 为 http:// 后用 urllib.parse.urlparse 解析
        - hostname → namespace
        - username → fs_id
        - password → password
        - path → path
        - query → query dict

        :param uri: URI 字符串，如 "disknext://my/docs/readme.md"
        :return: DiskNextURI 实例
        :raises ValueError: URI 格式无效
        """
        if not uri.startswith("disknext://"):
            raise ValueError(f"URI 必须以 disknext:// 开头: {uri}")

        # 替换协议为 http:// 以利用 urllib.parse 解析
        http_uri = "http://" + uri[len("disknext://"):]
        parsed = urlparse(http_uri)

        # 解析 namespace
        hostname = parsed.hostname
        if not hostname:
            raise ValueError(f"URI 缺少命名空间: {uri}")

        try:
            namespace = FileSystemNamespace(hostname)
        except ValueError:
            raise ValueError(f"无效的命名空间 '{hostname}'，有效值: {[e.value for e in FileSystemNamespace]}")

        # 解析 fs_id 和 password
        fs_id = unquote(parsed.username) if parsed.username else None
        password = unquote(parsed.password) if parsed.password else None

        # 解析 path
        path = unquote(parsed.path) if parsed.path else "/"
        if not path:
            path = "/"

        # 解析 query
        query: dict[str, str] | None = None
        if parsed.query:
            raw_query = parse_qs(parsed.query, keep_blank_values=True)
            query = {k: v[0] for k, v in raw_query.items()}

        return cls(
            fs_id=fs_id,
            namespace=namespace,
            path=path,
            password=password,
            query=query,
        )

    @classmethod
    def build(
        cls,
        namespace: FileSystemNamespace,
        path: str = "/",
        fs_id: str | None = None,
        password: str | None = None,
    ) -> "DiskNextURI":
        """
        构建 URI 实例

        :param namespace: 命名空间
        :param path: 路径
        :param fs_id: 文件系统标识符
        :param password: 访问密码
        :return: DiskNextURI 实例
        """
        # 确保 path 以 / 开头
        if not path.startswith("/"):
            path = "/" + path

        return cls(
            fs_id=fs_id,
            namespace=namespace,
            path=path,
            password=password,
        )

    # === 实例方法 ===

    def to_string(self) -> str:
        """
        序列化为 URI 字符串

        :return: URI 字符串，如 "disknext://my/docs/readme.md"
        """
        result = "disknext://"

        # fs_id 和 password
        if self.fs_id:
            result += quote(self.fs_id, safe="")
            if self.password:
                result += ":" + quote(self.password, safe="")
            result += "@"

        # namespace
        result += self.namespace.value

        # path
        result += self.path

        # query
        if self.query:
            result += "?" + urlencode(self.query)

        return result

    def join(self, *elements: str) -> "DiskNextURI":
        """
        拼接路径元素，返回新 URI

        :param elements: 路径元素
        :return: 新的 DiskNextURI 实例
        """
        base = self.path.rstrip("/")
        for element in elements:
            element = element.strip("/")
            if element:
                base += "/" + element

        if not base:
            base = "/"

        return DiskNextURI(
            fs_id=self.fs_id,
            namespace=self.namespace,
            path=base,
            password=self.password,
            query=self.query,
        )

    def dir_uri(self) -> "DiskNextURI":
        """
        返回父目录的 URI

        :return: 父目录的 DiskNextURI 实例
        """
        parts = self.path_parts
        if not parts:
            # 已经是根目录
            return self.root()

        parent_path = "/" + "/".join(parts[:-1])
        if not parent_path.endswith("/"):
            parent_path += "/"

        return DiskNextURI(
            fs_id=self.fs_id,
            namespace=self.namespace,
            path=parent_path,
            password=self.password,
        )

    def root(self) -> "DiskNextURI":
        """
        返回根目录的 URI（保留 namespace 和 fs_id）

        :return: 根目录的 DiskNextURI 实例
        """
        return DiskNextURI(
            fs_id=self.fs_id,
            namespace=self.namespace,
            path="/",
            password=self.password,
        )

    def name(self) -> str:
        """
        返回路径的最后一段（文件名或目录名）

        :return: 文件名或目录名，根目录返回空字符串
        """
        parts = self.path_parts
        return parts[-1] if parts else ""

    def __str__(self) -> str:
        return self.to_string()

    def __repr__(self) -> str:
        return f"DiskNextURI({self.to_string()!r})"
