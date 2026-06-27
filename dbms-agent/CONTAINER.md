# dbms-agent multi-architecture image

The Dockerfile supports `linux/amd64` and `linux/arm64`. Run commands from the
`dbms-agent` directory.

Build a multi-platform OCI archive locally:

```bash
chmod +x build-multiarch.sh
IMAGE=dbms-agent TAG=latest ./build-multiarch.sh
```

Build and push a multi-platform manifest to a registry:

```bash
IMAGE=registry.example.com/dbms/dbms-agent \
TAG=1.0.0 \
OUTPUT_MODE=push \
./build-multiarch.sh
```

Load a single architecture into the local Docker daemon:

```bash
PLATFORMS=linux/amd64 OUTPUT_MODE=load ./build-multiarch.sh
# On an ARM host, use PLATFORMS=linux/arm64.
```

Example runtime:

```bash
docker run -d --name dbms-agent \
  --restart unless-stopped \
  -p 5001:5001 \
  -e AGENT_API_KEY='replace-with-a-strong-key' \
  -e SECRET_KEY='replace-with-a-random-secret' \
  -e LOG_LEVEL=INFO \
  -v dbms-agent-backups:/data/backups \
  registry.example.com/dbms/dbms-agent:1.0.0
```

The image contains MySQL client tools, MongoDB Database Tools, `zstd`, OpenSSL,
and the Python drivers needed by instance probing. Use HTTPS between DBMS Server
and the agent when database credentials cross network boundaries. Backup policies
may explicitly set another path; otherwise the image defaults to `/data/backups`.
