FROM python:3.13-slim AS builder
WORKDIR /build
COPY pyproject.toml README.md COPYING LICENSE NOTICE ./
COPY src ./src
RUN python -m pip wheel --no-cache-dir --wheel-dir /wheels .

FROM python:3.13-slim
RUN groupadd --gid 10001 promptlibrary \
    && useradd --uid 10001 --gid 10001 --create-home promptlibrary \
    && mkdir -p /data && chown 10001:10001 /data
COPY --from=builder /wheels /wheels
RUN python -m pip install --no-cache-dir --no-index --find-links=/wheels promptlibrary \
    && rm -rf /wheels
USER 10001:10001
WORKDIR /home/promptlibrary
ENV PROMPTLIB_HOST=0.0.0.0 PROMPTLIB_PORT=8000 PROMPTLIB_DATA_DIR=/data \
    PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
VOLUME ["/data"]
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=3).read()"
CMD ["promptlibrary"]
