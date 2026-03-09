"""
Cython 编译脚本 — 将 ee/ 下的纯逻辑文件编译为 .so

用法：
    uv run --extra build python setup_cython.py build_ext --inplace

编译规则：
    - 跳过 __init__.py（Python 包发现需要）
    - 只编译 .py 文件（纯函数 / 服务逻辑）

编译后清理（Pro Docker 构建用）：
    uv run --extra build python setup_cython.py clean_artifacts
"""
import shutil
import sys
from pathlib import Path

EE_DIR = Path("ee")

# 跳过 __init__.py —— 包发现需要原始 .py
SKIP_NAMES = {"__init__.py"}


def _collect_modules() -> list[str]:
    """收集 ee/ 下需要编译的 .py 文件路径（点分模块名）。"""
    modules: list[str] = []
    for py_file in EE_DIR.rglob("*.py"):
        if py_file.name in SKIP_NAMES:
            continue
        # ee/license.py → ee.license
        module = str(py_file.with_suffix("")).replace("\\", "/").replace("/", ".")
        modules.append(module)
    return modules


def clean_artifacts() -> None:
    """删除已编译的 .py 源码、.c 中间文件和 build/ 目录。"""
    for py_file in EE_DIR.rglob("*.py"):
        if py_file.name in SKIP_NAMES:
            continue
        # 只删除有对应 .so / .pyd 的源文件
        parent = py_file.parent
        stem = py_file.stem
        has_compiled = (
            any(parent.glob(f"{stem}*.so")) or
            any(parent.glob(f"{stem}*.pyd"))
        )
        if has_compiled:
            py_file.unlink()
            print(f"已删除源码: {py_file}")

    # 删除 .c 中间文件
    for c_file in EE_DIR.rglob("*.c"):
        c_file.unlink()
        print(f"已删除中间文件: {c_file}")

    # 删除 build/ 目录
    build_dir = Path("build")
    if build_dir.exists():
        shutil.rmtree(build_dir)
        print(f"已删除: {build_dir}/")


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "clean_artifacts":
        clean_artifacts()
        sys.exit(0)

    # 动态导入（仅在编译时需要）
    from Cython.Build import cythonize
    from setuptools import Extension, setup

    modules = _collect_modules()
    if not modules:
        print("未找到需要编译的模块")
        sys.exit(0)

    print(f"即将编译以下模块: {modules}")

    extensions = [
        Extension(mod, [mod.replace(".", "/") + ".py"])
        for mod in modules
    ]

    setup(
        name="disknext-ee",
        packages=[],
        ext_modules=cythonize(
            extensions,
            compiler_directives={'language_level': "3"},
        ),
    )
