from datetime import datetime
from uuid import UUID

from sqlmodel import Field

from .base import SQLModelBase
from .color import ChromaticColor, NeutralColor, ThemeColorsBase
from .mixin import UUIDTableBaseMixin


class ThemePresetBase(SQLModelBase):
    """主题预设基础字段"""

    name: str = Field(max_length=100)
    """预设名称"""

    is_default: bool = False
    """是否为默认预设"""

    primary: ChromaticColor
    """主色调"""

    secondary: ChromaticColor
    """辅助色"""

    success: ChromaticColor
    """成功色"""

    info: ChromaticColor
    """信息色"""

    warning: ChromaticColor
    """警告色"""

    error: ChromaticColor
    """错误色"""

    neutral: NeutralColor
    """中性色"""


class ThemePreset(ThemePresetBase, UUIDTableBaseMixin):
    """主题预设表"""

    name: str = Field(max_length=100, unique=True)
    """预设名称（唯一约束）"""


# ==================== DTO ====================

class ThemePresetCreateRequest(SQLModelBase):
    """创建主题预设请求 DTO"""

    name: str = Field(max_length=100)
    """预设名称"""

    colors: ThemeColorsBase
    """颜色配置"""


class ThemePresetUpdateRequest(SQLModelBase):
    """更新主题预设请求 DTO"""

    name: str | None = Field(default=None, max_length=100)
    """预设名称（可选）"""

    colors: ThemeColorsBase | None = None
    """颜色配置（可选）"""


class ThemePresetResponse(SQLModelBase):
    """主题预设响应 DTO"""

    id: UUID
    """预设UUID"""

    name: str
    """预设名称"""

    is_default: bool
    """是否为默认预设"""

    colors: ThemeColorsBase
    """颜色配置"""

    created_at: datetime
    """创建时间"""

    updated_at: datetime
    """更新时间"""

    @classmethod
    def from_preset(cls, preset: ThemePreset) -> 'ThemePresetResponse':
        """从数据库模型转换为响应 DTO（平铺列 → 嵌套 colors 对象）"""
        return cls(
            id=preset.id,
            name=preset.name,
            is_default=preset.is_default,
            colors=ThemeColorsBase(
                primary=preset.primary,
                secondary=preset.secondary,
                success=preset.success,
                info=preset.info,
                warning=preset.warning,
                error=preset.error,
                neutral=preset.neutral,
            ),
            created_at=preset.created_at,
            updated_at=preset.updated_at,
        )


class ThemePresetListResponse(SQLModelBase):
    """主题预设列表响应 DTO"""

    themes: list[ThemePresetResponse]
    """主题预设列表"""
