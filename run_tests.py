#!/usr/bin/env python
"""
测试运行脚本

使用方式:
    python run_tests.py              # 运行所有测试
    python run_tests.py models       # 只运行模型测试
    python run_tests.py utils        # 只运行工具测试
    python run_tests.py service      # 只运行服务测试
    python run_tests.py --cov        # 带覆盖率运行
"""
import sys
import subprocess


def run_tests(target: str = "", coverage: bool = False):
    """运行测试"""
    cmd = ["pytest"]

    # 添加目标路径
    if target:
        if target == "models":
            cmd.append("tests/unit/models")
        elif target == "utils":
            cmd.append("tests/unit/utils")
        elif target == "service":
            cmd.append("tests/unit/service")
        else:
            cmd.append(target)
    else:
        cmd.append("tests/unit")

    # 添加覆盖率选项
    if coverage:
        cmd.extend(["--cov", "--cov-report=term-missing"])

    # 运行测试
    print(f"运行命令: {' '.join(cmd)}")
    result = subprocess.run(cmd)
    return result.returncode


if __name__ == "__main__":
    args = sys.argv[1:]

    target = ""
    coverage = False

    for arg in args:
        if arg == "--cov":
            coverage = True
        else:
            target = arg

    exit_code = run_tests(target, coverage)
    sys.exit(exit_code)
