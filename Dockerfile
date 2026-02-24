FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim

WORKDIR /app

# Install Python dependencies first (cached layer)
COPY pyproject.toml README.md LICENSE ./
RUN mkdir -p nanocrew && touch nanocrew/__init__.py && \
    uv pip install --system --no-cache . && \
    rm -rf nanocrew

# Copy the full source and install
COPY nanocrew/ nanocrew/
RUN uv pip install --system --no-cache .

# Create config directory
RUN mkdir -p /root/.nanocrew

# Gateway default port
EXPOSE 18790

ENTRYPOINT ["nanocrew"]
CMD ["status"]
