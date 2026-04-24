from .auth_identity import (
    AuthProviderType,
    ChangePasswordRequest,
)
from .scope import (
    Scope,
    ScopeAction,
    ScopeResource,
    ScopeSet,
    ScopeValueEnum,
    ScopeVisibility,
    ADMIN_SCOPES,
    USER_DEFAULT_SCOPES,
    WEBDAV_SCOPES,
)
from .token import (
    AccessTokenBase,
    RefreshTokenBase,
    TokenResponse,
)
from .user import (
    JWTPayload,
    MagicLinkRequest,
    UnifiedAuthRequest,
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
    DownloadStatus,
    DownloadType,
    Aria2TestRequest,
)
from .node import (
    Node,
    NodeStatus,
    NodeType,
)
from .group import (
    Group, GroupBase, GroupClaims, GroupOptionsBase, GroupAllOptionsBase, GroupResponse,
    # 管理员DTO
    GroupCreateRequest, GroupUpdateRequest, GroupDetailResponse, GroupListResponse,
)
from .file import (
    CreateFileRequest,
    CreateUploadSessionRequest,
    DirectoryCreateRequest,
    DirectoryResponse,
    Entry,
    EntryBase,
    EntryCopyRequest,
    EntryDeleteRequest,
    EntryFileFinalize,
    EntryMoveRequest,
    EntryMoveUpdate,
    EntryPropertyDetailResponse,
    EntryPropertyResponse,
    EntryUpdateRequest,
    EntryResponse,
    EntrySwitchPolicyRequest,
    EntryType,
    FileCategory,
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
    TextContentResponse,
    PatchContentRequest,
    PatchContentResponse,
    SourceLinkResponse
)
from .file_metadata import (
    EntryMetadata,
    EntryMetadataBase,
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
from .order import (
    Order, OrderStatus, OrderType,
    CreateOrderRequest, OrderResponse,
)
from .policy import (
    Policy, PolicyBase, PolicyCreateRequest,
    PolicyType, PolicySummary, PolicyUpdateRequest,
)
from .product import (
    Product, ProductBase, ProductType, PaymentMethod,
    ProductCreateRequest, ProductUpdateRequest, ProductResponse,
)
from .redeem import (
    Redeem, RedeemType,
    RedeemCreateRequest, RedeemUseRequest, RedeemInfoResponse, RedeemAdminResponse,
)
from .report import Report, ReportReason
from .server_config import (
    ServerConfig, ServerConfigBase, ServerConfigUpdateRequest,
    CaptchaType, ViewMethod, PWADisplayMode,
    SiteConfigResponse, AuthMethodConfig,
)
from .mail_template import MailTemplate, MailTemplateType
from .share import (
    Share, ShareBase, ShareCreateRequest, CreateShareResponse, ShareResponse,
    ShareOwnerInfo, ShareObjectItem, ShareDetailResponse,
    AdminShareListItem,
)
from .source_link import SourceLink
from .storage_pack import StoragePack, StoragePackResponse
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

from .captcha import (
    CaptchaRequestBase,
    CaptchaBase,
    CaptchaScene,
)

# 通用分页模型
from sqlmodel_ext import ListResponse

# 注册 PostgreSQL 触发器（必须在 metadata.create_all 之前 import 本模块）
from . import triggers  # noqa: F401
