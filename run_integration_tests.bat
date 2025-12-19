@echo off
chcp 65001 >nul
REM DiskNext Server 集成测试运行脚本

echo ==================== DiskNext Server 集成测试 ====================
echo.

REM 检查 uv 是否安装
echo 检查 uv...
uv --version >nul 2>&1
if errorlevel 1 (
    echo X uv 未安装，请先安装 uv: https://docs.astral.sh/uv/
    pause
    exit /b 1
)

REM 同步依赖
echo 同步依赖...
uv sync
echo.

REM 显示测试环境信息
echo 测试环境信息:
uv run python --version
uv run pytest --version
echo.

REM 运行测试
echo ==================== 开始运行集成测试 ====================
echo.

if "%1"=="site" (
    echo 运行站点端点测试...
    uv run pytest tests/integration/api/test_site.py -v
) else if "%1"=="user" (
    echo 运行用户端点测试...
    uv run pytest tests/integration/api/test_user.py -v
) else if "%1"=="admin" (
    echo 运行管理员端点测试...
    uv run pytest tests/integration/api/test_admin.py -v
) else if "%1"=="directory" (
    echo 运行目录操作测试...
    uv run pytest tests/integration/api/test_directory.py -v
) else if "%1"=="object" (
    echo 运行对象操作测试...
    uv run pytest tests/integration/api/test_object.py -v
) else if "%1"=="auth" (
    echo 运行认证中间件测试...
    uv run pytest tests/integration/middleware/test_auth.py -v
) else if "%1"=="api" (
    echo 运行所有 API 测试...
    uv run pytest tests/integration/api/ -v
) else if "%1"=="middleware" (
    echo 运行所有中间件测试...
    uv run pytest tests/integration/middleware/ -v
) else if "%1"=="coverage" (
    echo 运行测试并生成覆盖率报告...
    uv run pytest tests/integration/ -v --cov --cov-report=html
    echo.
    echo 覆盖率报告已生成: htmlcov/index.html
) else if "%1"=="unit" (
    echo 运行所有单元测试...
    uv run pytest tests/unit/ -v
) else if "%1"=="all" (
    echo 运行所有测试...
    uv run pytest tests/ -v
) else (
    echo 运行所有集成测试...
    uv run pytest tests/integration/ -v
)

echo.
echo ==================== 测试完成 ====================
pause