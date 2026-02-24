from .auth_identity import (
    AuthIdentity,
    AuthIdentityResponse,
    AuthProviderType,
    BindIdentityRequest,
    ChangePasswordRequest,
)
from .user import (
    BatchDeleteRequest,
    JWTPayload,
    MagicLinkRequest,
    UnifiedLoginRequest,
    UnifiedRegisterRequest,
    RefreshTokenRequest,
    AccessTokenBase,
    RefreshTokenBase,
    TokenResponse,
    User,
    UserBase,
    UserStorageResponse,
    UserPublic,
    UserResponse,
    UserSettingResponse,
    UserThemeUpdateRequest,
    SettingOption,
    UserSettingUpdateRequest,
    WebAuthnInfo,
    UserTwoFactorResponse,
    # 管理员DTO
    UserAdminUpdateRequest,
    UserCalibrateResponse,
    UserAdminDetailResponse,
)
from .user_authn import (
    AuthnDetailResponse,
    AuthnFinishRequest,
    AuthnRenameRequest,
    UserAuthn,
)
from .color import ChromaticColor, NeutralColor, ThemeColorsBase, BUILTIN_DEFAULT_COLORS
from .theme_preset import (
    ThemePreset, ThemePresetBase,
    ThemePresetCreateRequest, ThemePresetUpdateRequest,
    ThemePresetResponse, ThemePresetListResponse,
)

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
from .group import (
    Group, GroupBase, GroupClaims, GroupOptions, GroupOptionsBase, GroupAllOptionsBase, GroupResponse,
    # 管理员DTO
    GroupCreateRequest, GroupUpdateRequest, GroupDetailResponse, GroupListResponse,
)
from .object import (
    CreateFileRequest,
    CreateUploadSessionRequest,
    DirectoryCreateRequest,
    DirectoryResponse,
    Object,
    ObjectBase,
    ObjectCopyRequest,
    ObjectDeleteRequest,
    ObjectFileFinalize,
    ObjectMoveRequest,
    ObjectMoveUpdate,
    ObjectPropertyDetailResponse,
    ObjectPropertyResponse,
    ObjectRenameRequest,
    ObjectResponse,
    ObjectSwitchPolicyRequest,
    ObjectType,
    PolicyResponse,
    UploadChunkResponse,
    UploadSession,
    UploadSessionBase,
    UploadSessionResponse,
    # 管理员DTO
    AdminFileResponse,
    AdminFileListResponse,
    FileBanRequest,
    # 回收站DTO
    TrashItemResponse,
    TrashRestoreRequest,
    TrashDeleteRequest,
)
from .object_metadata import (
    ObjectMetadata,
    ObjectMetadataBase,
    MetadataNamespace,
    MetadataResponse,
    MetadataPatchItem,
    MetadataPatchRequest,
    INTERNAL_NAMESPACES,
    USER_WRITABLE_NAMESPACES,
)
from .custom_property import (
    CustomPropertyDefinition,
    CustomPropertyDefinitionBase,
    CustomPropertyType,
    CustomPropertyCreateRequest,
    CustomPropertyUpdateRequest,
    CustomPropertyResponse,
)
from .physical_file import PhysicalFile, PhysicalFileBase
from .uri import DiskNextURI, FileSystemNamespace
from .order import Order, OrderStatus, OrderType
from .policy import (
    Policy, PolicyBase, PolicyCreateRequest, PolicyOptions, PolicyOptionsBase,
    PolicyType, PolicySummary, PolicyUpdateRequest,
)
from .redeem import Redeem, RedeemType
from .report import Report, ReportReason
from .setting import (
    Setting, SettingsType, SiteConfigResponse, AuthMethodConfig,
    # 管理员DTO
    SettingItem, SettingsListResponse, SettingsUpdateRequest, SettingsUpdateResponse,
)
from .share import (
    Share, ShareBase, ShareCreateRequest, CreateShareResponse, ShareResponse,
    ShareOwnerInfo, ShareObjectItem, ShareDetailResponse,
    AdminShareListItem,
)
from .source_link import SourceLink
from .storage_pack import StoragePack
from .tag import Tag, TagType
from .task import Task, TaskProps, TaskPropsBase, TaskStatus, TaskType, TaskSummary, TaskSummaryBase
from .webdav import (
    WebDAV, WebDAVBase,
    WebDAVCreateRequest, WebDAVUpdateRequest, WebDAVAccountResponse,
)
from .file_app import (
    FileApp, FileAppType, FileAppExtension, FileAppGroupLink, UserFileAppDefault,
    # DTO
    FileAppSummary, FileViewersResponse, SetDefaultViewerRequest, UserFileAppDefaultResponse,
    FileAppCreateRequest, FileAppUpdateRequest, FileAppResponse, FileAppListResponse,
    ExtensionUpdateRequest, GroupAccessUpdateRequest, WopiSessionResponse,
    WopiDiscoveredExtension, WopiDiscoveryResponse,
)
from .wopi import WopiFileInfo, WopiAccessTokenPayload

from .database_connection import DatabaseManager

from .model_base import (
    MCPBase,
    MCPMethod,
    MCPRequestBase,
    MCPResponseBase,
    ResponseBase,
    # Admin Summary DTO
    MetricsSummary,
    LicenseInfo,
    VersionInfo,
    AdminSummaryResponse,
)

# 通用分页模型
from sqlmodel_ext import ListResponse
