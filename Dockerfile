FROM ghcr.io/astral-sh/uv:python3.13-bookworm-slim

WORKDIR /app

COPY pyproject.toml uv.lock ./

RUN uv sync --frozen --no-dev

COPY . .

EXPOSE 5213

CMD ["uv", "run", "fastapi", "run", "main.py", "--host", "0.0.0.0", "--port", "5213"]