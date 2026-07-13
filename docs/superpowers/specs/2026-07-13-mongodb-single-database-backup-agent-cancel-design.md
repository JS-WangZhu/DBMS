# MongoDB 单库部分备份与 Agent 任务停止设计

## 目标

MongoDB 部分备份只选择一个数据库，并在一条 `mongodump` 命令中排除该库内的多个集合。备份记录中的 `command` 必须是一维参数数组，不得保存或执行批量命令列表。

同时修复 Agent 执行备份时停止任务不可靠的问题，使普通、gzip 和 zstd 执行路径创建的全部子进程都能被任务取消接口定位并终止。

## 配置模型

MongoDB 专属配置继续保存在 `BackupPolicy.extra_json.mongo_backup`：

```json
{
  "mode": "partial",
  "database": "app",
  "excluded_collections": ["audit_events", "temporary_data"]
}
```

- `mode=full` 时规范化为 `database=""`、`excluded_collections=[]`。
- `mode=partial` 时 `database` 去除首尾空格后必须非空。
- `excluded_collections` 必须是数组；每项去除首尾空格后必须非空且不得重复。
- 允许排除零个集合，此时语义是只备份指定数据库的全部集合。
- 该配置只适用于 MongoDB。
- 旧配置仅在所有有效集合排除项都属于同一数据库、且不存在整库排除项时自动转换；其他旧配置返回明确错误，要求用户重新配置。

## 命令与产物

部分备份命令形态为：

```text
mongodump --host=<host> --port=<port> --db=<database> --archive=<file> --excludeCollection=<collection-1> --excludeCollection=<collection-2>
```

认证参数按现有逻辑追加。压缩行为保持现有策略语义：

- `none`：使用单条 `mongodump` 写入 `.archive`。
- `gzip`：同一条命令追加 `--gzip`，写入 `.archive`。
- `zstd`：单条 `mongodump --archive=-` 输出到现有 zstd 管道；备份记录仍只保存这一条 `mongodump` 参数数组。

本地执行器和 Agent 使用相同的单命令构造规则。部分备份不再连接 MongoDB 枚举数据库、不再创建逐库临时目录、不再循环执行 `mongodump`，也不再额外打包 tar。

Dry run 返回同样的一维命令数组和最终产物路径。

## 前端交互

MongoDB 策略表单在选择“部分备份”后显示：

- 一个必填的目标数据库输入框。
- 一个可增删的排除集合列表；每行只填写集合名。

保存前校验目标数据库、空集合名和重复集合名。编辑策略时回显新配置；可无歧义转换的旧配置按新结构回显。

## Agent 进程管理与取消

每个 Agent 备份任务维护当前活动子进程集合，而不是只保存某个执行分支偶然写入的单一 `process` 字段。

- 普通 dump、gzip dump、zstd 的 dump 与压缩进程启动后立即登记。
- 子进程结束后在 `finally` 中注销，避免任务表持有失效进程。
- 取消接口先设置 `cancel_requested`，再对该任务的全部活动进程调用 `terminate()`。
- 工作线程完成时，如果 `cancel_requested` 为真，最终状态保持 `cancelled`，不得被子进程退出错误覆盖为 `failed`。
- 已结束任务的重复取消保持幂等。
- 取消不触发备份失败通知。

本次只要求可靠终止本 Agent 进程内登记的子进程；Agent 重启后恢复进程句柄不在范围内。

## 错误处理

- 无效部分备份配置在策略保存或更新时返回 400。
- Agent 取消请求找不到任务时返回 404；已是终态时返回当前快照。
- 取消过程中某个进程已经自然退出时忽略该进程，继续处理其他活动进程。
- 命令失败、压缩失败、加密和上传失败沿用现有失败路径。

## 测试

### Backend

- 规范化单库与多个排除集合。
- 拒绝空数据库、空集合项和重复集合项。
- 兼容可无歧义转换的旧配置，拒绝无法转换的旧配置。
- 本地执行器生成一条一维 `mongodump` 命令，不枚举数据库、不循环执行。
- dry run 和执行记录的 `command` 均为同一条命令。

### Agent

- 单库部分备份生成一条命令及多个 `--excludeCollection`。
- gzip 和 zstd 执行路径登记并注销全部子进程。
- 取消接口终止已登记进程，并最终保持 `cancelled`。
- 重复取消保持幂等。

### Frontend 与回归

- 新配置构造与旧配置回显正确。
- 前端构建通过。
- MongoDB 完全备份、MySQL 备份、加密、S3 和远程结果同步的既有测试继续通过。

## 验收标准

- MongoDB 部分备份配置只包含一个目标数据库和零到多个排除集合。
- 实际只启动一次 `mongodump`，命令包含一个 `--db` 和对应的多个 `--excludeCollection`。
- 备份记录只保存一条一维命令，不出现批量命令嵌套数组。
- Agent 执行的普通、gzip、zstd 备份均可停止，实际子进程被终止且最终状态为 `cancelled`。
- 完全备份及非相关备份功能保持兼容。
