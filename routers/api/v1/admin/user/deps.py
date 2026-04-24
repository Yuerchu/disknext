from sqlalchemy import and_
from sqlalchemy.sql.elements import ColumnElement
from sqlmodel_ext import cond

from sqlmodels import User
from sqlmodels.user import UserFilterParams


def build_user_filter_condition(filter_params: UserFilterParams) -> ColumnElement[bool] | None:
    """将 UserFilterParams 转为 SQLAlchemy WHERE 条件"""
    conditions: list[ColumnElement[bool]] = []

    if filter_params.group_id is not None:
        conditions.append(cond(User.group_id == filter_params.group_id))
    if filter_params.email_contains is not None:
        conditions.append(cond(User.email.ilike(f"%{filter_params.email_contains}%")))
    if filter_params.nickname_contains is not None:
        conditions.append(cond(User.nickname.ilike(f"%{filter_params.nickname_contains}%")))
    if filter_params.status is not None:
        conditions.append(cond(User.status == filter_params.status))

    if not conditions:
        return None
    return and_(*conditions)
