# DBMS 外部调用 API 手册

该文档详细说明了 DBMS 平台提供给外部系统（如工单系统、CI/CD 平台）调用的接口。

## 1. 认证说明

所有外部接口均需在 HTTP 请求头中携带 `X-API-Key` 进行认证。
API Key 可在 DBMS 平台的“备份管理 -> 备份密钥管理”或相关安全配置页面生成。

- **Header 示例**: `X-API-Key: YOUR_SECRET_TOKEN`

---

## 2. 集群信息查询

获取当前用户有权访问的集群列表，用于后续接口的 `cluster_id` 参数。

- **接口地址**: `/api/v1/external/clusters`
- **请求方法**: `GET`
- **认证方式**: `X-API-Key`

### 响应示例
```json
{
  "code": 200,
  "data": [
    {
      "id": 1,
      "name": "生产 MySQL 集群",
      "db_type": "mysql",
      "environment": "prod",
      "product": "支付业务",
      "instance_count": 3,
      "databases": ["db1", "db2"]
    }
  ],
  "message": "success"
}
```

---

## 3. 统一执行接口

支持对 MySQL、MongoDB、Redis 进行数据变更或命令执行。

- **接口地址**: `/api/v1/external/execute`
- **请求方法**: `POST`
- **请求参数 (JSON)**:

| 参数名 | 类型 | 必填 | 说明 |
| :--- | :--- | :--- | :--- |
| `db_type` | string | 是 | `mysql` \| `mongodb` \| `redis` |
| `cluster_id` | integer | 是 | 集群 ID |
| `database` | string | 条件 | 数据库/Schema 名称（MySQL/MongoDB 必填） |
| `statement` | string | 是 | 执行语句（支持多条 SQL 换行，或原生命令） |
| `product` | string | 否 | 项目组名称（校验用，与集群配置一致） |
| `environment` | string | 否 | 环境名称（校验用，与集群配置一致） |
| `timeout_seconds` | integer | 否 | 超时秒数，默认 86400 |
| `execution_id` | string | 否 | 外部自定义执行 ID |

### 请求示例 (MySQL)
```json
{
  "db_type": "mysql",
  "cluster_id": 1,
  "database": "test_db",
  "product": "支付业务",
  "environment": "prod",
  "statement": "UPDATE users SET status = 1 WHERE id = 100;\nINSERT INTO audit_logs (msg) VALUES ('test');"
}
```

---

## 4. AI 智能审计接口

利用 AI 对待执行的语句进行风险评估和可行性分析。AI 会参考表的数据量（行数/大小）给出精准建议。

- **接口地址**: `/api/v1/external/ai-analyze`
- **请求方法**: `POST`
- **请求参数 (JSON)**:

| 参数名 | 类型 | 必填 | 说明 |
| :--- | :--- | :--- | :--- |
| `db_type` | string | 是 | `mysql` \| `mongodb` |
| `cluster_id` | integer | 是 | 集群 ID |
| `database` | string | 是 | 数据库名称 |
| `statement` | string | 是 | 待分析的 SQL 或命令文本 |
| `product` | string | 否 | 项目组名称（校验用，与集群配置一致） |
| `environment` | string | 否 | 环境名称（校验用，与集群配置一致） |

### 响应结果说明
- `can_release`: **关键字段**。布尔值，`true` 表示建议放行，`false` 表示不建议放行。
- `analysis`: 详细的 Markdown 格式分析报告，包含逐行评估和优化建议。

### 响应示例
```json
{
  "code": 200,
  "data": {
    "can_release": false,
    "analysis": "### 1. **逐行评估**\n- `DROP TABLE users`: [禁止执行] - 高危操作...\n### 4. **最终结论**\n[不建议放行] - 存在删除表操作。",
    "cluster_name": "生产集群",
    "db_type": "mysql"
  },
  "message": "success"
}
```

### 请求示例
```bash
curl -X POST http://your-dbms-domain/api/v1/external/ai-analyze \
  -H "Content-Type: application/json" \
  -H "X-API-Key: YOUR_SECRET_API_KEY" \
  -d '{
    "db_type": "mysql",
    "cluster_id": 1,
    "database": "test_db",
    "product": "支付业务",
    "environment": "prod",
    "statement": "SELECT * FROM users;\nUPDATE users SET status=1;"
  }'
```

---

## 5. 错误码说明

| 状态码 | 说明 |
| :--- | :--- |
| 401 | API Key 缺失或无效 |
| 403 | 无权访问该集群或该功能 |
| 400 | 参数缺失或格式错误 |
| 500 | 内部执行错误（包含数据库报错） |
