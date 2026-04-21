"""
Scope 权限检查依赖注入

用法::

    from middleware.scope import require_scope

    @router.post("/share", dependencies=[Depends(require_scope("shares:create:own"))])
    async def create_share(...): ...
"""
from typing import Annotated

from fastapi import Depends

from middleware.auth import auth_required
from sqlmodels.scope import ScopeSet
from sqlmodels.user import User
from utils import http_exceptions


def require_scope(required_scope: str):
    """
    静态 scope 检查依赖工厂。

    管理员（group.admin=True）直接通过，不检查 scopes。
    普通用户从 User.scopes 构建 ScopeSet 并匹配。

    :param required_scope: 需要的 scope，如 ``files:read:own``
    """
    async def _checker(user: Annotated[User, Depends(auth_required)]) -> User:
        if user.group.admin:
            return user
        scope_set = ScopeSet.from_strings(user.scopes or [])
        if not scope_set.has(required_scope):
            http_exceptions.raise_forbidden(f"缺少权限: {required_scope}")
        return user

    return _checker
