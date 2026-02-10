"""
DiskNextURI 模型的单元测试
"""
import pytest

from sqlmodels.uri import DiskNextURI, FileSystemNamespace


class TestDiskNextURIParse:
    """测试 URI 解析"""

    def test_parse_my_root(self):
        """测试解析个人空间根目录"""
        uri = DiskNextURI.parse("disknext://my/")
        assert uri.namespace == FileSystemNamespace.MY
        assert uri.path == "/"
        assert uri.fs_id is None
        assert uri.password is None
        assert uri.is_root is True

    def test_parse_my_with_path(self):
        """测试解析个人空间带路径"""
        uri = DiskNextURI.parse("disknext://my/docs/readme.md")
        assert uri.namespace == FileSystemNamespace.MY
        assert uri.path == "/docs/readme.md"
        assert uri.fs_id is None
        assert uri.path_parts == ["docs", "readme.md"]
        assert uri.is_root is False

    def test_parse_my_with_fs_id(self):
        """测试解析带 fs_id 的个人空间"""
        uri = DiskNextURI.parse("disknext://some-uuid@my/docs")
        assert uri.namespace == FileSystemNamespace.MY
        assert uri.fs_id == "some-uuid"
        assert uri.path == "/docs"

    def test_parse_share_with_code(self):
        """测试解析分享链接"""
        uri = DiskNextURI.parse("disknext://abc123@share/")
        assert uri.namespace == FileSystemNamespace.SHARE
        assert uri.fs_id == "abc123"
        assert uri.path == "/"
        assert uri.password is None

    def test_parse_share_with_password(self):
        """测试解析带密码的分享链接"""
        uri = DiskNextURI.parse("disknext://abc123:mypass@share/sub/dir")
        assert uri.namespace == FileSystemNamespace.SHARE
        assert uri.fs_id == "abc123"
        assert uri.password == "mypass"
        assert uri.path == "/sub/dir"

    def test_parse_trash(self):
        """测试解析回收站"""
        uri = DiskNextURI.parse("disknext://trash/")
        assert uri.namespace == FileSystemNamespace.TRASH
        assert uri.is_root is True

    def test_parse_with_query(self):
        """测试解析带查询参数的 URI"""
        uri = DiskNextURI.parse("disknext://my/?name=report&type=file")
        assert uri.namespace == FileSystemNamespace.MY
        assert uri.query is not None
        assert uri.query["name"] == "report"
        assert uri.query["type"] == "file"

    def test_parse_invalid_scheme(self):
        """测试无效的协议前缀"""
        with pytest.raises(ValueError, match="disknext://"):
            DiskNextURI.parse("http://my/docs")

    def test_parse_invalid_namespace(self):
        """测试无效的命名空间"""
        with pytest.raises(ValueError, match="无效的命名空间"):
            DiskNextURI.parse("disknext://invalid/docs")

    def test_parse_no_namespace(self):
        """测试缺少命名空间"""
        with pytest.raises(ValueError):
            DiskNextURI.parse("disknext://")


class TestDiskNextURIBuild:
    """测试 URI 构建"""

    def test_build_simple(self):
        """测试简单构建"""
        uri = DiskNextURI.build(FileSystemNamespace.MY)
        assert uri.namespace == FileSystemNamespace.MY
        assert uri.path == "/"
        assert uri.fs_id is None

    def test_build_with_path(self):
        """测试带路径构建"""
        uri = DiskNextURI.build(FileSystemNamespace.MY, path="/docs/readme.md")
        assert uri.path == "/docs/readme.md"

    def test_build_path_auto_prefix(self):
        """测试路径自动添加 / 前缀"""
        uri = DiskNextURI.build(FileSystemNamespace.MY, path="docs/readme.md")
        assert uri.path == "/docs/readme.md"

    def test_build_with_fs_id(self):
        """测试带 fs_id 构建"""
        uri = DiskNextURI.build(
            FileSystemNamespace.SHARE,
            fs_id="abc123",
            password="secret",
        )
        assert uri.fs_id == "abc123"
        assert uri.password == "secret"


class TestDiskNextURIToString:
    """测试 URI 序列化"""

    def test_to_string_simple(self):
        """测试简单序列化"""
        uri = DiskNextURI.build(FileSystemNamespace.MY)
        assert uri.to_string() == "disknext://my/"

    def test_to_string_with_path(self):
        """测试带路径序列化"""
        uri = DiskNextURI.build(FileSystemNamespace.MY, path="/docs/readme.md")
        assert uri.to_string() == "disknext://my/docs/readme.md"

    def test_to_string_with_fs_id(self):
        """测试带 fs_id 序列化"""
        uri = DiskNextURI.build(FileSystemNamespace.MY, fs_id="uuid-123")
        assert uri.to_string() == "disknext://uuid-123@my/"

    def test_to_string_with_password(self):
        """测试带密码序列化"""
        uri = DiskNextURI.build(
            FileSystemNamespace.SHARE,
            fs_id="code",
            password="pass",
        )
        assert uri.to_string() == "disknext://code:pass@share/"

    def test_to_string_roundtrip(self):
        """测试序列化-反序列化往返"""
        original = "disknext://abc123:pass@share/sub/dir"
        uri = DiskNextURI.parse(original)
        result = uri.to_string()
        assert result == original


class TestDiskNextURIId:
    """测试 id() 方法"""

    def test_id_with_fs_id(self):
        """测试有 fs_id 时返回 fs_id"""
        uri = DiskNextURI.build(FileSystemNamespace.MY, fs_id="my-uuid")
        assert uri.id("default") == "my-uuid"

    def test_id_without_fs_id(self):
        """测试无 fs_id 时返回默认值"""
        uri = DiskNextURI.build(FileSystemNamespace.MY)
        assert uri.id("default-uuid") == "default-uuid"

    def test_id_without_fs_id_no_default(self):
        """测试无 fs_id 且无默认值时返回 None"""
        uri = DiskNextURI.build(FileSystemNamespace.MY)
        assert uri.id() is None


class TestDiskNextURIJoin:
    """测试 join() 方法"""

    def test_join_single(self):
        """测试拼接单个路径元素"""
        uri = DiskNextURI.build(FileSystemNamespace.MY, path="/docs")
        joined = uri.join("readme.md")
        assert joined.path == "/docs/readme.md"

    def test_join_multiple(self):
        """测试拼接多个路径元素"""
        uri = DiskNextURI.build(FileSystemNamespace.MY)
        joined = uri.join("docs", "work", "report.pdf")
        assert joined.path == "/docs/work/report.pdf"

    def test_join_preserves_metadata(self):
        """测试 join 保留 namespace 和 fs_id"""
        uri = DiskNextURI.build(FileSystemNamespace.SHARE, fs_id="code123")
        joined = uri.join("sub")
        assert joined.namespace == FileSystemNamespace.SHARE
        assert joined.fs_id == "code123"


class TestDiskNextURIDirUri:
    """测试 dir_uri() 方法"""

    def test_dir_uri_file(self):
        """测试获取文件的父目录 URI"""
        uri = DiskNextURI.build(FileSystemNamespace.MY, path="/docs/readme.md")
        parent = uri.dir_uri()
        assert parent.path == "/docs/"

    def test_dir_uri_root(self):
        """测试根目录的 dir_uri 返回自身"""
        uri = DiskNextURI.build(FileSystemNamespace.MY, path="/")
        parent = uri.dir_uri()
        assert parent.path == "/"


class TestDiskNextURIRoot:
    """测试 root() 方法"""

    def test_root_resets_path(self):
        """测试 root 重置路径"""
        uri = DiskNextURI.build(
            FileSystemNamespace.MY,
            path="/docs/work/report.pdf",
            fs_id="uuid-123",
        )
        root = uri.root()
        assert root.path == "/"
        assert root.fs_id == "uuid-123"
        assert root.namespace == FileSystemNamespace.MY


class TestDiskNextURIName:
    """测试 name() 方法"""

    def test_name_file(self):
        """测试获取文件名"""
        uri = DiskNextURI.build(FileSystemNamespace.MY, path="/docs/readme.md")
        assert uri.name() == "readme.md"

    def test_name_directory(self):
        """测试获取目录名"""
        uri = DiskNextURI.build(FileSystemNamespace.MY, path="/docs/work")
        assert uri.name() == "work"

    def test_name_root(self):
        """测试根目录的 name 返回空字符串"""
        uri = DiskNextURI.build(FileSystemNamespace.MY, path="/")
        assert uri.name() == ""


class TestDiskNextURIProperties:
    """测试属性方法"""

    def test_path_parts(self):
        """测试路径分割"""
        uri = DiskNextURI.build(FileSystemNamespace.MY, path="/docs/work/report.pdf")
        assert uri.path_parts == ["docs", "work", "report.pdf"]

    def test_path_parts_root(self):
        """测试根路径分割"""
        uri = DiskNextURI.build(FileSystemNamespace.MY, path="/")
        assert uri.path_parts == []

    def test_is_root_true(self):
        """测试 is_root 为真"""
        uri = DiskNextURI.build(FileSystemNamespace.MY, path="/")
        assert uri.is_root is True

    def test_is_root_false(self):
        """测试 is_root 为假"""
        uri = DiskNextURI.build(FileSystemNamespace.MY, path="/docs")
        assert uri.is_root is False

    def test_str_representation(self):
        """测试字符串表示"""
        uri = DiskNextURI.build(FileSystemNamespace.MY, path="/docs")
        assert str(uri) == "disknext://my/docs"

    def test_repr(self):
        """测试 repr"""
        uri = DiskNextURI.build(FileSystemNamespace.MY, path="/docs")
        assert "disknext://my/docs" in repr(uri)
