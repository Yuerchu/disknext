"""
Scope 权限系统单元测试

覆盖 Scope 解析、匹配逻辑和 ScopeSet 批量检查。
"""
import pytest

from sqlmodels.scope import (
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


class TestScopeParse:
    """Scope.parse() 解析测试"""

    def test_parse_full_format(self):
        scope = Scope.parse("files:read:own")
        assert scope.resource == ScopeResource.FILES
        assert scope.action == ScopeAction.READ
        assert scope.visibility == ScopeVisibility.OWN

    def test_parse_wildcard_format(self):
        scope = Scope.parse("files:*")
        assert scope.resource == ScopeResource.FILES
        assert scope.action == ScopeAction.WILDCARD
        assert scope.visibility is None

    def test_parse_admin_resource(self):
        scope = Scope.parse("admin.users:read:all")
        assert scope.resource == ScopeResource.ADMIN_USERS
        assert scope.action == ScopeAction.READ
        assert scope.visibility == ScopeVisibility.ALL

    def test_parse_admin_wildcard(self):
        scope = Scope.parse("admin.settings:*")
        assert scope.resource == ScopeResource.ADMIN_SETTINGS
        assert scope.action == ScopeAction.WILDCARD

    def test_parse_download_action(self):
        scope = Scope.parse("files:download:own")
        assert scope.action == ScopeAction.DOWNLOAD
        assert scope.visibility == ScopeVisibility.OWN

    def test_parse_invalid_format_one_part(self):
        with pytest.raises(ValueError, match="2 或 3 段"):
            Scope.parse("files")

    def test_parse_invalid_format_four_parts(self):
        with pytest.raises(ValueError, match="2 或 3 段"):
            Scope.parse("files:read:own:extra")

    def test_parse_invalid_resource(self):
        with pytest.raises(ValueError):
            Scope.parse("unknown:read:own")

    def test_parse_invalid_action(self):
        with pytest.raises(ValueError):
            Scope.parse("files:execute:own")

    def test_parse_invalid_visibility(self):
        with pytest.raises(ValueError):
            Scope.parse("files:read:public")

    def test_parse_two_part_non_wildcard_rejected(self):
        with pytest.raises(ValueError, match="action 必须是"):
            Scope.parse("files:read")

    def test_parse_wildcard_with_visibility_rejected(self):
        with pytest.raises(ValueError, match="不应有 visibility"):
            Scope.parse("files:*:own")


class TestScopeMatches:
    """Scope.matches() 匹配测试"""

    def test_exact_match(self):
        held = Scope.parse("files:read:own")
        required = Scope.parse("files:read:own")
        assert held.matches(required)

    def test_wildcard_matches_any_action(self):
        held = Scope.parse("files:*")
        assert held.matches(Scope.parse("files:read:own"))
        assert held.matches(Scope.parse("files:write:all"))
        assert held.matches(Scope.parse("files:delete:own"))
        assert held.matches(Scope.parse("files:download:own"))

    def test_all_contains_own(self):
        held = Scope.parse("files:read:all")
        assert held.matches(Scope.parse("files:read:own"))

    def test_own_does_not_contain_all(self):
        held = Scope.parse("files:read:own")
        assert not held.matches(Scope.parse("files:read:all"))

    def test_different_resource_no_match(self):
        held = Scope.parse("files:read:own")
        assert not held.matches(Scope.parse("shares:read:own"))

    def test_different_action_no_match(self):
        held = Scope.parse("files:read:own")
        assert not held.matches(Scope.parse("files:write:own"))

    def test_wildcard_does_not_cross_resource(self):
        held = Scope.parse("files:*")
        assert not held.matches(Scope.parse("shares:read:own"))

    def test_admin_wildcard(self):
        held = Scope.parse("admin.users:*")
        assert held.matches(Scope.parse("admin.users:read:all"))
        assert held.matches(Scope.parse("admin.users:delete:own"))
        assert not held.matches(Scope.parse("admin.groups:read:all"))


class TestScopeSet:
    """ScopeSet 批量匹配测试"""

    def test_has_with_exact_scope(self):
        ss = ScopeSet.from_strings(["files:read:own", "files:write:own"])
        assert ss.has("files:read:own")
        assert ss.has("files:write:own")
        assert not ss.has("files:delete:own")

    def test_has_with_wildcard(self):
        ss = ScopeSet.from_strings(["files:*"])
        assert ss.has("files:read:own")
        assert ss.has("files:delete:all")

    def test_has_with_all_visibility(self):
        ss = ScopeSet.from_strings(["shares:read:all"])
        assert ss.has("shares:read:own")
        assert ss.has("shares:read:all")
        assert not ss.has("shares:write:own")

    def test_empty_set_has_nothing(self):
        ss = ScopeSet.from_strings([])
        assert not ss.has("files:read:own")

    def test_admin_scopes_cover_all(self):
        ss = ScopeSet.from_strings(ADMIN_SCOPES)
        assert ss.has("files:read:own")
        assert ss.has("files:delete:all")
        assert ss.has("shares:create:own")
        assert ss.has("webdav:write:own")
        assert ss.has("admin.users:read:all")
        assert ss.has("admin.settings:write:all")

    def test_user_default_scopes(self):
        ss = ScopeSet.from_strings(USER_DEFAULT_SCOPES)
        assert ss.has("files:read:own")
        assert ss.has("shares:create:own")
        assert not ss.has("files:read:all")
        assert not ss.has("webdav:read:own")
        assert not ss.has("admin.users:read:all")


class TestScopeValueEnum:
    """ScopeValueEnum 自动生成测试"""

    def test_wildcard_values_exist(self):
        assert ScopeValueEnum("files:*")
        assert ScopeValueEnum("admin.users:*")

    def test_full_values_exist(self):
        assert ScopeValueEnum("files:read:own")
        assert ScopeValueEnum("shares:create:all")
        assert ScopeValueEnum("admin.settings:write:all")

    def test_invalid_value_raises(self):
        with pytest.raises(ValueError):
            ScopeValueEnum("nonexistent:read:own")

    def test_all_default_scopes_are_valid_enum_values(self):
        for s in USER_DEFAULT_SCOPES:
            assert isinstance(s, ScopeValueEnum)

    def test_all_admin_scopes_are_valid_enum_values(self):
        for s in ADMIN_SCOPES:
            assert isinstance(s, ScopeValueEnum)

    def test_all_webdav_scopes_are_valid_enum_values(self):
        for s in WEBDAV_SCOPES:
            assert isinstance(s, ScopeValueEnum)


class TestScopeStr:
    """Scope.__str__() 测试"""

    def test_full_format(self):
        assert str(Scope.parse("files:read:own")) == "files:read:own"

    def test_wildcard_format(self):
        assert str(Scope.parse("files:*")) == "files:*"
