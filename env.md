# 环境变量字段

- `MODE` str 运行模式，默认 `master`
  - `master` 主机模式
  - `slave` 从机模式
- `DEBUG` bool 是否开启调试模式，默认 `false`
- `DATABASE_URL`: 数据库连接信息，默认 `sqlite+aiosqlite:///disknext.db`
- `REDIS_HOST`: Redis 主机地址
- `REDIS_PORT`: Redis 端口
- `REDIS_PASSWORD`: Redis 密码
- `REDIS_DB`: Redis 数据库
- `REDIS_PROTOCOL`: Redis 协议
