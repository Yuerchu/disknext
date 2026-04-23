FROM ghcr.io/astral-sh/uv:python3.14-bookworm-slim

# 使用 copy 模式创建 venv，避免 Docker 跨 stage COPY 丢失硬链接
ENV UV_LINK_MODE=copy

WORKDIR /app

COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev

COPY . .
COPY statics/ /app/statics/

ENV PATH="/app/.venv/bin:${PATH}"
EXPOSE 5213
CMD ["fastapi", "run", "main.py", "--host", "0.0.0.0", "--port", "5213"]
