from .user import (
    LoginRequest,
    RegisterRequest,
    TokenResponse,
    User,
    UserBase,
    UserPublic,
    UserResponse,
    UserSettingResponse,
    WebAuthnInfo,
)
from .user_authn import AuthnResponse, UserAuthn
from .color import ThemeResponse

from .download import (
    Download,
    DownloadAria2File,
    DownloadAria2Info,
    DownloadAria2InfoBase,
    DownloadStatus,
    DownloadType,
)
from .node import (
    Aria2Configuration,
    Aria2ConfigurationBase,
    Node,
    NodeStatus,
    NodeType,
)
from .group import Group, GroupBase, GroupOptions, GroupOptionsBase, GroupResponse
from .object import (
    CreateFileRequest,
    CreateUploadSessionRequest,
    DirectoryCreateRequest,
    DirectoryResponse,
    FileMetadata,
    FileMetadataBase,
    Object,
    ObjectBase,
    ObjectCopyRequest,
    ObjectDeleteRequest,
    ObjectMoveRequest,
    ObjectPropertyDetailResponse,
    ObjectPropertyResponse,
    ObjectRenameRequest,
    ObjectResponse,
    ObjectType,
    PolicyResponse,
    UploadChunkResponse,
    UploadSession,
    UploadSessionBase,
    UploadSessionResponse,
)
from .physical_file import PhysicalFile, PhysicalFileBase
from .order import Order, OrderStatus, OrderType
from .policy import Policy, PolicyOptions, PolicyOptionsBase, PolicyType
from .redeem import Redeem, RedeemType
from .report import Report, ReportReason
from .setting import Setting, SettingsType, SiteConfigResponse
from .share import Share
from .source_link import SourceLink
from .storage_pack import StoragePack
from .tag import Tag, TagType
from .task import Task, TaskProps, TaskPropsBase, TaskStatus, TaskType
from .webdav import WebDAV

from .database import engine, get_session


import uuid
from sqlmodel import Field
from .base import SQLModelBase

class ResponseBase(SQLModelBase):
    """通用响应模型"""

    instance_id: uuid.UUID = Field(default_factory=uuid.uuid4)
    """实例ID，用于标识请求的唯一性"""