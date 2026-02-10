"""
乐观锁 Mixin

提供基于 SQLAlchemy version_id_col 机制的乐观锁支持。

乐观锁适用场景：
- 涉及"状态转换"的表（如：待支付 -> 已支付）
- 涉及"数值变动"的表（如：余额、库存）

不适用场景：
- 日志表、纯插入表、低价值统计表
- 能用 UPDATE table SET col = col + 1 解决的简单计数问题

使用示例：
    class Order(OptimisticLockMixin, UUIDTableBaseMixin, table=True):
        status: OrderStatusEnum
        amount: Decimal

    # save/update 时自动检查版本号
    # 如果版本号不匹配（其他事务已修改），会抛出 OptimisticLockError
    try:
        order = await order.save(session)
    except OptimisticLockError as e:
        # 处理冲突：重新查询并重试，或报错给用户
        l.warning(f"乐观锁冲突: {e}")
"""
from typing import ClassVar

from sqlalchemy.orm.exc import StaleDataError


class OptimisticLockError(Exception):
    """
    乐观锁冲突异常

    当 save/update 操作检测到版本号不匹配时抛出。
    这意味着在读取和写入之间，其他事务已经修改了该记录。

    Attributes:
        model_class: 发生冲突的模型类名
        record_id: 记录 ID（如果可用）
        expected_version: 期望的版本号（如果可用）
        original_error: 原始的 StaleDataError
    """

    def __init__(
            self,
            message: str,
            model_class: str | None = None,
            record_id: str | None = None,
            expected_version: int | None = None,
            original_error: StaleDataError | None = None,
    ):
        super().__init__(message)
        self.model_class = model_class
        self.record_id = record_id
        self.expected_version = expected_version
        self.original_error = original_error


class OptimisticLockMixin:
    """
    乐观锁 Mixin

    使用 SQLAlchemy 的 version_id_col 机制实现乐观锁。
    每次 UPDATE 时自动检查并增加版本号，如果版本号不匹配（即其他事务已修改），
    session.commit() 会抛出 StaleDataError，被 save/update 方法捕获并转换为 OptimisticLockError。

    原理：
    1. 每条记录有一个 version 字段，初始值为 0
    2. 每次 UPDATE 时，SQLAlchemy 生成的 SQL 类似：
       UPDATE table SET ..., version = version + 1 WHERE id = ? AND version = ?
    3. 如果 WHERE 条件不匹配（version 已被其他事务修改），
       UPDATE 影响 0 行，SQLAlchemy 抛出 StaleDataError

    继承顺序：
        OptimisticLockMixin 必须放在 TableBaseMixin/UUIDTableBaseMixin 之前：
        class Order(OptimisticLockMixin, UUIDTableBaseMixin, table=True):
            ...

    配套重试：
        如果加了乐观锁，业务层需要处理 OptimisticLockError：
        - 报错给用户："数据已被修改，请刷新后重试"
        - 自动重试：重新查询最新数据并再次尝试
    """
    _has_optimistic_lock: ClassVar[bool] = True
    """标记此类启用了乐观锁"""

    version: int = 0
    """乐观锁版本号，每次更新自动递增"""
