
from typing import Optional, List, TYPE_CHECKING
from sqlmodel import Field, Relationship, text
from .base import TableBase
from enum import StrEnum

if TYPE_CHECKING:
    from .file import File
    from .folder import Folder

class PolicyType(StrEnum):
    LOCAL = "local"
    S3 = "s3"

class Policy(TableBase, table=True):
    """存储策略模型"""

    name: str = Field(max_length=255, unique=True)
    """策略名称"""

    type: PolicyType
    """存储策略类型"""

    server: str | None = Field(default=None, max_length=255)
    """服务器地址（本地策略为绝对路径）"""

    bucket_name: str | None = Field(default=None, max_length=255)
    """存储桶名称"""

    is_private: bool = Field(default=True, sa_column_kwargs={"server_default": text("true")})
    """是否为私有空间"""

    base_url: str | None = Field(default=None, max_length=255)
    """访问文件的基础URL"""

    access_key: str | None = Field(default=None)
    """Access Key"""

    secret_key: str | None = Field(default=None)
    """Secret Key"""
    max_size: int = Field(default=0, sa_column_kwargs={"server_default": "0"})
    """允许上传的最大文件尺寸（字节）"""

    auto_rename: bool = Field(default=False, sa_column_kwargs={"server_default": text("false")})
    """是否自动重命名"""

    dir_name_rule: str | None = Field(default=None, max_length=255)
    """目录命名规则"""

    file_name_rule: str | None = Field(default=None, max_length=255)
    """文件命名规则"""

    is_origin_link_enable: bool = Field(default=False, sa_column_kwargs={"server_default": text("false")})
    """是否开启源链接访问"""
    
    options: str | None = Field(default=None)
    """其他选项 (JSON格式)"""
    # options 示例: {"token":"","file_type":null,"mimetype":"","od_redirect":"http://127.0.0.1:8000/...","chunk_size":52428800,"s3_path_style":false}
    
    # 关系
    files: List["File"] = Relationship(back_populates="policy")
    folders: List["Folder"] = Relationship(back_populates="policy")
    
    @staticmethod
    async def create(
        policy: Optional["Policy"] = None,
        **kwargs
    ):
        pass