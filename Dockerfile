# ============================================================
# 基础层：安装运行时依赖（CE 依赖，不含 EE）
# ============================================================
FROM ghcr.io/astral-sh/uv:python3.14-bookworm-slim AS base

# 使用 copy 模式创建 venv，避免 Docker 跨 stage COPY 丢失硬链接
ENV UV_LINK_MODE=copy

WORKDIR /app

COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev

COPY . .

# ============================================================
# Community 版本：删除 ee/ 目录
# ============================================================
FROM base AS community

RUN rm -rf ee/
COPY statics/ /app/statics/

ENV PATH="/app/.venv/bin:${PATH}"
EXPOSE 5213
CMD ["fastapi", "run", "main.py", "--host", "0.0.0.0", "--port", "5213"]

# ============================================================
# Pro 编译层：Rust (maturin) + Cython 编译 ee/ 模块
# ============================================================
FROM base AS pro-builder

# 安装 Rust 工具链 (编译 ee/_license_core) 和 gcc (Cython)
RUN apt-get update && \
    apt-get install -y --no-install-recommends gcc libc6-dev curl ca-certificates && \
    curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh -s -- -y --default-toolchain stable --profile minimal && \
    rm -rf /var/lib/apt/lists/*

ENV PATH="/root/.cargo/bin:${PATH}"

# 安装 EE 依赖（触发 maturin 编译 disknext_license）+ Cython 构建依赖
RUN uv sync --frozen --no-dev --extra ee --extra build

# Cython 编译 ee/ 下的 Python 模块并清理源码
RUN uv run python setup_cython.py build_ext --inplace && \
    uv run python setup_cython.py clean_artifacts

# 清理 Rust crate 源码（disknext_license 已通过 maturin 安装到 .venv，源码不再需要）
RUN rm -rf ee/_license_core

# ============================================================
# Pro 版本：运行时镜像（无编译工具链，直接复用 builder 的 .venv）
# ============================================================
FROM ghcr.io/astral-sh/uv:python3.14-bookworm-slim AS pro

WORKDIR /app

COPY --from=pro-builder /app/ /app/
COPY statics/ /app/statics/

# 直接用 venv 的 fastapi，跳过 uv 的 sync 检查
# (避免因 ee/_license_core 源码已被清理而触发 editable 依赖重解析失败)
ENV PATH="/app/.venv/bin:${PATH}"
EXPOSE 5213
CMD ["fastapi", "run", "main.py", "--host", "0.0.0.0", "--port", "5213"]
