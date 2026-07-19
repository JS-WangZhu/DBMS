# syntax=docker/dockerfile:1.7
FROM python:3.11-slim-bookworm

ARG TARGETARCH
ARG PG_MAJOR=18
ARG MONGO_TOOLS_VERSION=100.11.0

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    FLASK_ENV=production \
    AGENT_HOST=0.0.0.0 \
    AGENT_PORT=5001 \
    BACKUP_ROOT=/data/backups \
    PATH=/usr/lib/postgresql/${PG_MAJOR}/bin:${PATH}

RUN set -eux; \
    apt-get update; \
    apt-get install -y --no-install-recommends \
        ca-certificates \
        curl \
        default-mysql-client \
        openssl \
        tini \
        zstd; \
    install -d -m 0755 /usr/share/postgresql-common/pgdg; \
    curl -fsSLo /usr/share/postgresql-common/pgdg/apt.postgresql.org.asc \
        https://www.postgresql.org/media/keys/ACCC4CF8.asc; \
    dpkg_arch="$(dpkg --print-architecture)"; \
    printf '%s\n' \
        'Types: deb' \
        'URIs: https://apt.postgresql.org/pub/repos/apt' \
        'Suites: bookworm-pgdg' \
        'Components: main' \
        "Architectures: ${dpkg_arch}" \
        'Signed-By: /usr/share/postgresql-common/pgdg/apt.postgresql.org.asc' \
        > /etc/apt/sources.list.d/pgdg.sources; \
    apt-get update; \
    apt-get install -y --no-install-recommends "postgresql-client-${PG_MAJOR}"; \
    image_arch="${TARGETARCH:-${dpkg_arch}}"; \
    case "${image_arch}" in \
        amd64) mongo_platform="debian12"; mongo_arch="x86_64" ;; \
        arm64) mongo_platform="ubuntu2204"; mongo_arch="arm64" ;; \
        *) echo "Unsupported architecture: ${image_arch}" >&2; exit 1 ;; \
    esac; \
    curl -fsSLo /tmp/mongodb-tools.tgz \
        "https://fastdl.mongodb.org/tools/db/mongodb-database-tools-${mongo_platform}-${mongo_arch}-${MONGO_TOOLS_VERSION}.tgz"; \
    mkdir -p /tmp/mongodb-tools; \
    tar -xzf /tmp/mongodb-tools.tgz --strip-components=1 -C /tmp/mongodb-tools; \
    install -m 0755 /tmp/mongodb-tools/bin/* /usr/local/bin/; \
    if ! command -v mysqldump >/dev/null 2>&1 && command -v mariadb-dump >/dev/null 2>&1; then \
        ln -s "$(command -v mariadb-dump)" /usr/local/bin/mysqldump; \
    fi; \
    command -v pg_dump; \
    pg_dump --version | grep -Eq "PostgreSQL\) ${PG_MAJOR}([.]|$)"; \
    command -v mysqldump; \
    mysqldump --version; \
    command -v mongodump; \
    mongodump --version; \
    rm -rf /tmp/mongodb-tools /tmp/mongodb-tools.tgz /var/lib/apt/lists/*

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
