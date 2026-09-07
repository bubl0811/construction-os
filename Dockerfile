FROM python:3.12-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app

COPY pyproject.toml README.md requirements.lock ./
COPY app ./app
RUN pip install --no-cache-dir --require-hashes -r requirements.lock \
    && pip install --no-cache-dir --no-deps .

COPY alembic.ini ./
COPY migrations ./migrations

RUN useradd --system --uid 10001 --user-group appuser \
    && mkdir -p /var/lib/construction-os/documents \
    && chown appuser:appuser /var/lib/construction-os/documents
USER 10001:10001

EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--no-server-header"]
