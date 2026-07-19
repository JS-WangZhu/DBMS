# dbms-agent

Backup execution agent for DBMS. This service runs on each data center and executes backup commands remotely triggered by the main DBMS backend.

## Architecture

```
┌─────────────────────┐         HTTP         ┌─────────────────────┐
│    DBMS 主项目      │ ──────────────────►  │    dbms-agent       │
│                     │   POST /execute       │                     │
│  - 策略管理(CRUD)   │                       │  - 执行备份命令      │
│  - 日志记录         │ ◄──────────────────   │  - S3 上传          │
│  - 调度推送         │   执行结果/日志ID      │  - 通知(可选)       │
└─────────────────────┘                       └─────────────────────┘
         │
         ▼ 共享数据库
    ┌──────────┐
    │ PostgreSQL│
    └──────────┘
```

## Quick Start

### 1. Install Dependencies

```bash
pip install -r requirements.txt
```

### 2. Configure

Copy `.env.example` to `.env` and configure:

```bash
cp .env.example .env
```

Key configuration:
- `DATABASE_URL` - Must match the main project's database
- `FERNET_KEY` - Must match the main project's SECRET_KEY for password decryption

### 3. Run

```bash
python manage.py
```

The agent will start on `http://localhost:5001` by default.

### 4. Test Health Check

```bash
curl http://localhost:5001/api/agent/health
```

## Main Project Configuration

To enable remote agent in the main project, add to `.env`:

```env
BACKUP_AGENT_URL=http://localhost:5001
ENABLE_REMOTE_AGENT=true
```

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/agent/health` | Health check |
| POST | `/api/agent/execute` | Submit backup and return `task_id` |
| GET | `/api/agent/tasks/<task_id>` | Get in-memory task status/result |
| POST | `/api/agent/tasks/status` | Batch task status/result query |
| GET | `/api/agent/version` | Get agent version |

### Execute Backup

```bash
curl -X POST http://localhost:5001/api/agent/execute \
  -H "Content-Type: application/json" \
  -d '{"policy_id": 1, "dry_run": false}'
```

## Deployment

For each data center:

1. Deploy `dbms-agent` on a machine that can access the database instances
2. Configure `DATABASE_URL` to point to the shared PostgreSQL database
3. Ensure `FERNET_KEY` matches the main project
4. Set `BACKUP_AGENT_URL` in the main project to point to this agent

Backup task state is intentionally process-local memory. Run one agent worker
per endpoint (the built-in `python manage.py` setup already does this). If a
multi-worker process manager is used, requests for one endpoint must be pinned
to the same worker or the task store must be replaced with a shared store.


## Docker multi-architecture build

The image supports `linux/amd64` and `linux/arm64` and includes `pg_dump` 18,
`mysqldump`, and `mongodump`.

Build and load an image for the current machine:

```bash
docker buildx build --platform linux/amd64 -t dbms-agent:local --load .
# On an ARM64 machine, use: --platform linux/arm64
```

Publish one multi-architecture tag:

```bash
docker buildx build \
  --platform linux/amd64,linux/arm64 \
  -t registry.example.com/dbms-agent:latest \
  --push .
```

Run the agent with a persistent backup directory and a required API key:

```bash
docker run -d --name dbms-agent \
  -p 5001:5001 \
  -e AGENT_API_KEY=replace-with-a-strong-shared-key \
  -v /data/dbms-backups:/data/backups \
  registry.example.com/dbms-agent:latest
```

Remote backup policies must use `/data/backups` (or a subdirectory) as their
storage path so backup files are written to the mounted volume.
