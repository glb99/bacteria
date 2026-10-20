FROM ghcr.io/astral-sh/uv:python3.14-bookworm-slim

WORKDIR /app

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    PATH="/app/.venv/bin:$PATH"

COPY pyproject.toml uv.lock ./
COPY backend ./backend

RUN uv sync --frozen --no-dev --all-packages

WORKDIR /app/backend/app

EXPOSE 8000

CMD ["sh", "-c", "alembic upgrade head && python -m app.initial_data && uvicorn app.main:app --host 0.0.0.0 --port 8000"]
