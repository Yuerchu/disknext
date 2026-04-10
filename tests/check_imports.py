#!/usr/bin/env python
"""
检查测试所需的所有导入是否可用

运行此脚本以验证测试环境配置是否正确。
"""
import sys
import traceback


def check_import(module_name: str, description: str) -> bool:
    """检查单个模块导入"""
    try:
        __import__(module_name)
        print(f"✅ {description}: {module_name}")
        return True
    except ImportError as e:
        print(f"❌ {description}: {module_name}")
        print(f"   错误: {e}")
        return False


def main():
    """主检查函数"""
    print("=" * 60)
    print("DiskNext Server 测试环境检查")
    print("=" * 60)
    print()

    checks = [
        # 测试框架
        ("pytest", "测试框架"),
        ("pytest_asyncio", "异步测试支持"),

        # 数据库
        ("sqlmodel", "SQLModel ORM"),
        ("sqlalchemy", "SQLAlchemy"),
        ("asyncpg", "异步 PostgreSQL 驱动"),
        ("redis", "Redis 异步客户端"),

        # FastAPI
        ("fastapi", "FastAPI 框架"),
        ("httpx", "HTTP 客户端"),

        # 工具库
        ("loguru", "日志库"),
        ("argon2", "密码哈希"),
        ("jwt", "JWT 令牌"),
        ("pyotp", "TOTP 两步验证"),
        ("itsdangerous", "签名工具"),

        # 项目模块
        ("sqlmodels", "数据库模型"),
        ("sqlmodels.user", "用户模型"),
        ("sqlmodels.group", "用户组模型"),
        ("sqlmodels.object", "对象模型"),
        ("sqlmodels.setting", "设置模型"),
        ("sqlmodels.policy", "策略模型"),
        ("sqlmodels.database", "数据库连接"),
        ("utils.password.pwd", "密码工具"),
        ("utils.JWT.JWT", "JWT 工具"),
        ("service.user.login", "登录服务"),
    ]

    results = []
    for module, desc in checks:
        result = check_import(module, desc)
        results.append((module, desc, result))

    print()
    print("=" * 60)
    print("检查结果")
    print("=" * 60)

    success_count = sum(1 for _, _, result in results if result)
    total_count = len(results)

    print(f"成功: {success_count}/{total_count}")

    failed = [(m, d) for m, d, r in results if not r]
    if failed:
        print()
        print("失败的导入:")
        for module, desc in failed:
            print(f"  - {desc}: {module}")
        print()
        print("请运行以下命令安装依赖:")
        print("  uv sync")
        print("  或")
        print("  pip install -e .")
        return 1
    else:
        print()
        print("✅ 所有检查通过! 测试环境配置正确。")
        print()
        print("运行测试:")
        print("  pytest                    # 运行所有测试")
        print("  pytest --cov              # 带覆盖率运行")
        print("  python run_tests.py       # 使用测试脚本")
        return 0


if __name__ == "__main__":
    try:
        exit_code = main()
    except Exception as e:
        print()
        print("=" * 60)
        print("检查过程中发生错误:")
        print("=" * 60)
        traceback.print_exc()
        exit_code = 1

    sys.exit(exit_code)
