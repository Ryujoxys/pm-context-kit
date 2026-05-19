FROM python:3.11-slim

RUN apt-get update && \
    apt-get install -y --no-install-recommends git ripgrep ca-certificates && \
    apt-get clean && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY pyproject.toml ./
COPY src ./src
RUN pip install --no-cache-dir .

RUN useradd -r -u 10001 appuser
USER appuser

EXPOSE 8000

ENTRYPOINT ["code-context-mcp"]
