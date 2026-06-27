# syntax=docker/dockerfile:1.7
FROM python:3.11-slim-bookworm

ARG TARGETARCH
ARG MONGO_TOOLS_VERSION=100.11.0

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    FLASK_ENV=production \
    AGENT_HOST=0.0.0.0 \
    AGENT_PORT=5001 \
    BACKUP_ROOT=/data/backups

RUN set -eux; \
    apt-get update; \
    apt-get install -y --no-install-recommends \
        ca-certificates \
        curl \
        default-mysql-client \
        openssl \
        tini \
        zstd; \
    case "${TARGETARCH}" in \
        amd64) mongo_arch="x86_64" ;; \
        arm64) mongo_arch="arm64" ;; \
        *) echo "Unsupported architecture: ${TARGETARCH}" >&2; exit 1 ;; \
    esac; \
    curl -fsSLo /tmp/mongodb-tools.deb \
        "https://fastdl.mongodb.org/tools/db/mongodb-database-tools-debian12-${mongo_arch}-${MONGO_TOOLS_VERSION}.deb"; \
    apt-get install -y --no-install-recommends /tmp/mongodb-tools.deb; \
    rm -f /tmp/mongodb-tools.deb; \
    rm -rf /var/lib/apt/lists/*

WORKDIR /opt/dbms-agent

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app
COPY manage.py ./manage.py

RUN groupadd --gid 10001 dbms-agent \
    && useradd --uid 10001 --gid dbms-agent --home-dir /opt/dbms-agent --shell /usr/sbin/nologin dbms-agent \
    && mkdir -p "${BACKUP_ROOT}" \
    && chown -R dbms-agent:dbms-agent /opt/dbms-agent "${BACKUP_ROOT}"

USER dbms-agent

EXPOSE 5001
VOLUME ["/data/backups"]

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD curl -fsS "http://127.0.0.1:${AGENT_PORT}/api/agent/health" || exit 1

ENTRYPOINT ["/usr/bin/tini", "--"]
CMD ["python", "manage.py"]
