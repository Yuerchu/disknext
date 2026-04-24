from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import model_validator
from sqlmodel import Field

from sqlmodel_ext import SQLModelBase, UUIDTableBaseMixin, Str100

from .color import ChromaticColor, NeutralColor, ThemeColorsBase


class ThemePresetBase(SQLModelBase):
    """主题预设基础字段"""

    name: Str100
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

    name: Str100 = Field(unique=True)
    """预设名称（唯一约束）"""


# ==================== DTO ====================

class ThemePresetCreateRequest(SQLModelBase):
    """创建主题预设请求 DTO"""

    name: Str100
    """预设名称"""

    colors: ThemeColorsBase
    """颜色配置"""


class ThemePresetUpdateRequest(SQLModelBase):
    """更新主题预设请求 DTO"""

    name: Str100 | None = None
    """预设名称（可选）"""

    colors: ThemeColorsBase | None = None
    """颜色配置（可选）"""


class ThemePresetResponse(SQLModelBase):
    """主题预设响应 DTO"""

    id: UUID
    """预设UUID"""

    name: Str100
    """预设名称"""

    is_default: bool
    """是否为默认预设"""

    colors: ThemeColorsBase
    """颜色配置"""

    created_at: datetime
    """创建时间"""

    updated_at: datetime
    """更新时间"""

    _COLOR_KEYS: tuple[str, ...] = (
        'primary', 'secondary', 'success', 'info', 'warning', 'error', 'neutral',
    )

    @model_validator(mode='before')
    @classmethod
    def _nest_colors(cls, data: Any) -> Any:
        """从平铺颜色字段自动构建嵌套 colors 对象"""
        if isinstance(data, dict):
            if 'colors' in data:
                return data
            data['colors'] = {k: data.pop(k) for k in cls._COLOR_KEYS if k in data}
            return data
        # from_attributes: ORM 对象，提取为 dict
        if hasattr(data, 'colors'):
            return data
        result: dict[str, Any] = {}
        for name in cls.model_fields:
            if name != 'colors' and hasattr(data, name):
                result[name] = getattr(data, name)
        result['colors'] = {k: getattr(data, k) for k in cls._COLOR_KEYS if hasattr(data, k)}
        return result


class ThemePresetListResponse(SQLModelBase):
    """主题预设列表响应 DTO"""

    themes: list[ThemePresetResponse]
    """主题预设列表"""
