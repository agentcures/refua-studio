FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

COPY pyproject.toml README.md LICENSE ./
COPY src ./src

RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir .

RUN useradd --create-home --uid 10001 studio && \
    mkdir -p /data && \
    chown -R studio:studio /data /app

USER studio

EXPOSE 8787

CMD ["refua-studio", "--host", "0.0.0.0", "--port", "8787", "--data-dir", "/data", "--workspace-root", "/workspace"]
