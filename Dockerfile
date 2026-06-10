FROM python:3.12-slim

# Install uv.
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

WORKDIR /app

# Copy only dependency definition files first – this layer will be cached
# as long as pyproject.toml and uv.lock remain unchanged.
COPY pyproject.toml uv.lock /app/

# Install dependencies into a virtual environment.
RUN uv sync --frozen --no-cache

# Now copy the rest of the application code (main.py, etc.).
# IMPORTANT: ensure .venv is listed in .dockerignore so it does NOT
# overwrite the environment we just installed.
COPY . /app

EXPOSE 5001
CMD ["uv", "run", "main.py"]