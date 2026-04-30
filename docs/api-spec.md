# API 设计（v1）

Base URL: `/api/v1`

## Auth

- `POST /auth/login` 登录（local/ldap）
- `GET /auth/me` 获取当前用户信息
- `PATCH /auth/password` 当前用户修改密码

## Users (admin)

- `GET /users` 用户列表
- `POST /users` 创建用户
- `PATCH /users/{id}` 更新用户状态/角色/密码

## Clusters

- `GET /clusters` 查询集群
- `POST /clusters` 创建集群
- `PATCH /clusters/{id}` 更新集群

## Instances

- `GET /instances?db_type=mysql` 按数据库类型查询
- `POST /instances` 创建实例
- `PATCH /instances/{id}` 更新实例
- `POST /instances/{id}/resolve` 手动刷新域名解析

## Monitoring

- `POST /monitoring/collect/{instance_id}` 手动采集
- `GET /monitoring/latest/{instance_id}` 最新监控快照

## Dedicated Database APIs

- `GET/POST /mysql/instances`
- `GET /mysql/instances/{id}/replication`
- `GET/POST /mongodb/instances`
- `GET /mongodb/instances/{id}/replica-status`
- `GET/POST /redis/instances`
- `GET /redis/instances/{id}/cluster-health`
- `GET/POST /doris/instances`
- `GET /doris/instances/{id}/fe-status`

## Backup

- `GET /backups/policies` 策略列表
- `POST /backups/policies` 创建策略
- `PATCH /backups/policies/{id}` 更新策略
- `POST /backups/run/{policy_id}` 立即执行备份
- `GET /backups/logs` 备份日志（支持 `db_type/status/policy_id/keyword/start_at/end_at/page/page_size`）
- `GET /backups/overview?hours=24` 最近备份成功失败统计（含小时级图表序列）

## DNS

- `POST /dns/refresh` 批量刷新域名解析

## Health

- `GET /health` 服务健康状态
