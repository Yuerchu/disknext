#!/bin/bash

# DiskNext Server 集成测试运行脚本

echo "==================== DiskNext Server 集成测试 ===================="
echo ""

# 检查 uv 是否安装
echo "检查 uv..."
if ! command -v uv &> /dev/null; then
    echo "X uv 未安装，请先安装 uv: https://docs.astral.sh/uv/"
    exit 1
fi

# 同步依赖
echo "同步依赖..."
uv sync
echo ""

# 显示测试环境信息
echo "测试环境信息:"
uv run python --version
uv run pytest --version
echo ""

# 运行测试
echo "==================== 开始运行集成测试 ===================="
echo ""

# 根据参数选择测试范围
case "$1" in
    site)
        echo "运行站点端点测试..."
        uv run pytest tests/integration/api/test_site.py -v
        ;;
    user)
        echo "运行用户端点测试..."
        uv run pytest tests/integration/api/test_user.py -v
        ;;
    admin)
        echo "运行管理员端点测试..."
        uv run pytest tests/integration/api/test_admin.py -v
        ;;
    directory)
        echo "运行目录操作测试..."
        uv run pytest tests/integration/api/test_directory.py -v
        ;;
    object)
        echo "运行对象操作测试..."
        uv run pytest tests/integration/api/test_object.py -v
        ;;
    auth)
        echo "运行认证中间件测试..."
        uv run pytest tests/integration/middleware/test_auth.py -v
        ;;
    api)
        echo "运行所有 API 测试..."
        uv run pytest tests/integration/api/ -v
        ;;
    middleware)
        echo "运行所有中间件测试..."
        uv run pytest tests/integration/middleware/ -v
        ;;
    coverage)
        echo "运行测试并生成覆盖率报告..."
        uv run pytest tests/integration/ -v --cov --cov-report=html
        echo ""
        echo "覆盖率报告已生成: htmlcov/index.html"
        ;;
    unit)
        echo "运行所有单元测试..."
        uv run pytest tests/unit/ -v
        ;;
    all)
        echo "运行所有测试..."
        uv run pytest tests/ -v
        ;;
    *)
        echo "运行所有集成测试..."
        uv run pytest tests/integration/ -v
        ;;
esac

echo ""
echo "==================== 测试完成 ===================="