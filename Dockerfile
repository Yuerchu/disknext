# ============================================================
# 基础层：安装运行时依赖
# ============================================================
FROM ghcr.io/astral-sh/uv:python3.13-bookworm-slim AS base

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

EXPOSE 5213
CMD ["uv", "run", "fastapi", "run", "main.py", "--host", "0.0.0.0", "--port", "5213"]

# ============================================================
# Pro 编译层：Cython 编译 ee/ 模块
# ============================================================
FROM base AS pro-builder

RUN apt-get update && \
    apt-get install -y --no-install-recommends gcc libc6-dev && \
    rm -rf /var/lib/apt/lists/*

RUN uv sync --frozen --no-dev --extra build

RUN uv run python setup_cython.py build_ext --inplace && \
    uv run python setup_cython.py clean_artifacts

# ============================================================
# Pro 版本：包含编译后的 ee/ 模块（仅 __init__.py + .so）
# ============================================================
FROM ghcr.io/astral-sh/uv:python3.13-bookworm-slim AS pro

WORKDIR /app

COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev

COPY --from=pro-builder /app/ /app/
COPY statics/ /app/statics/

EXPOSE 5213
CMD ["uv", "run", "fastapi", "run", "main.py", "--host", "0.0.0.0", "--port", "5213"]
