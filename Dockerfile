# The AI service as deployed for the public demo: FastAPI plus the MCP server
# the spending assistant starts for each question. No embeddings extra and no
# database URL, so retrieval is off; the demo only uses the assistant.

# Build the MCP server (TypeScript) from its public repo at a pinned commit.
FROM node:22-slim AS mcp
ARG MCP_REPO=https://github.com/petryga/expense-tracker-mcp.git
ARG MCP_COMMIT=da4213aeed2965bff6edd2a2c9c1d172be36046f
RUN apt-get update && apt-get install -y --no-install-recommends git ca-certificates \
    && rm -rf /var/lib/apt/lists/*
WORKDIR /mcp
RUN git clone "$MCP_REPO" . && git checkout "$MCP_COMMIT"
# --ignore-scripts skips the husky git-hook setup; it isn't needed to build.
RUN npm ci --ignore-scripts && npx tsc && npm prune --omit=dev --ignore-scripts

FROM python:3.14-slim
# Node runs the MCP server as a subprocess; only the binary is needed.
COPY --from=mcp /usr/local/bin/node /usr/local/bin/node
COPY --from=mcp /mcp/package.json /opt/mcp/package.json
COPY --from=mcp /mcp/node_modules /opt/mcp/node_modules
COPY --from=mcp /mcp/dist /opt/mcp/dist

WORKDIR /app
COPY pyproject.toml ./
COPY app ./app
RUN pip install --no-cache-dir . && useradd --create-home --uid 10001 ai
USER ai

ENV MCP_SERVER_COMMAND=node \
    MCP_SERVER_ARGS=/opt/mcp/dist/index.js \
    PYTHONUNBUFFERED=1 \
    PORT=8000
EXPOSE 8000
CMD ["sh", "-c", "exec uvicorn app.main:app --host 0.0.0.0 --port ${PORT}"]
