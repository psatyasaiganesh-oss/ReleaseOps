FROM python:3.13-slim
ARG VERSION=1.0.0
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 HOST=0.0.0.0 PORT=8080 \
    DATABASE_PATH=/data/releaseops.db APP_VERSION=${VERSION}
WORKDIR /app
RUN groupadd --gid 10001 app && useradd --uid 10001 --gid app --no-create-home app \
    && mkdir -p /data && chown app:app /data
COPY --chown=app:app releaseops ./releaseops
COPY --chown=app:app scripts/backup.py ./scripts/backup.py
USER 10001:10001
EXPOSE 8080
HEALTHCHECK --interval=10s --timeout=3s --start-period=5s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8080/readyz', timeout=2)"
CMD ["python", "-m", "releaseops.server"]
