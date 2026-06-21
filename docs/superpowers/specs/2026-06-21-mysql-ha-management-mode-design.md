# MySQL HA 管理模式设计

## 目标

将 MySQL 集群现有的“是否启用 HA 切换”开关替换为明确的 HA 管理模式，区分未托管、Orchestrator 托管和 DBMS 托管。只有 DBMS 托管的集群允许通过 DBMS 平台执行 HA 操作。

## 模式定义

MySQL 集群新增 `ha_mode` 字段，允许以下值：

- `none`：默认值。未配置 HA 管理，不允许 DBMS 平台执行切换、提升或修复。
- `orc`：集群由 Orchestrator 平台托管。DBMS 只展示拓扑、状态和历史，不执行任何 HA 干预。
- `dbms`：集群由 DBMS 平台托管。允许在 DBMS 平台执行正常切换、故障切换、提升当前主库和集群修复。

非 MySQL 集群固定使用 `none`，不展示 HA 管理模式配置。

## 数据模型与兼容

- 在 `db_clusters` 表新增非空字符串字段 `ha_mode`，默认值为 `none`。
- 模型序列化返回 `ha_mode`。
- 现有集群升级时统一初始化为 `none`，不根据原有 `ha_switch_enabled` 自动启用 DBMS 托管。
- 删除业务代码对 `ha_switch_enabled` 的读写和判断。
- 数据库中的旧字段可暂时保留，避免在线升级执行删列带来的兼容风险，但不再作为业务依据，也不再通过 API 返回。

## 集群管理

MySQL 集群的创建和编辑页面使用“HA 管理模式”下拉框：

- 无：`none`
- Orchestrator：`orc`
- DBMS：`dbms`

创建集群时默认为“无”。编辑旧集群时，如果没有有效模式，同样显示“无”。

后端创建和更新接口校验模式值。非法值返回 400。非 MySQL 集群即使请求携带其他模式，也保存为 `none`。

## MySQL HA 页面

集群列表和拓扑详情展示 HA 管理模式标签：

- 无
- ORC 托管
- DBMS 托管

操作规则：

- `dbms`：显示并启用“高可用切换”入口及切换对话框。
- `orc`：隐藏或禁用切换入口，并提示“该集群由 Orchestrator 托管，DBMS 不进行切换干预”。
- `none`：隐藏或禁用切换入口，并提示“该集群未配置 DBMS HA 管理”。

三种模式均可查看拓扑、健康状态和历史记录。

## 后端安全边界

所有会改变 MySQL HA 状态的 DBMS 接口必须在服务端校验：

```text
cluster.db_type == "mysql" and cluster.ha_mode == "dbms"
```

覆盖：

- 普通 HA 切换接口。
- 流式 HA 切换接口。
- 正常切换。
- 故障切换。
- 提升当前主库。
- 集群修复。

不满足条件时返回 400：

- `orc`：说明该集群由 Orchestrator 托管，DBMS 不允许干预。
- `none`：说明该集群未启用 DBMS HA 管理。

前端限制仅用于交互提示，不能替代后端校验。

## 状态采集与展示

HA 模式不改变现有监控、拓扑采集、域名解析和历史记录逻辑：

- `ha_domain` 继续用于拓扑识别和状态展示。
- 调度器继续采集 MySQL 集群状态。
- ORC 模式不要求 DBMS 调用 Orchestrator API，也不新增 Orchestrator 配置。
- 本次仅定义管理归属和 DBMS 操作权限，不实现 ORC 平台集成。

## API 输出

集群相关 API 和 MCP 状态输出使用：

```json
{
  "ha_mode": "none"
}
```

不再输出或依赖 `ha_switch_enabled`。

## 测试

后端测试覆盖：

- 新建 MySQL 集群默认模式为 `none`。
- 合法模式可以创建和更新。
- 非法模式被拒绝。
- 非 MySQL 集群强制保存为 `none`。
- `none` 和 `orc` 模式拒绝普通及流式 HA 操作。
- `dbms` 模式可以进入现有 HA 执行流程。
- 模型和 MCP 输出包含 `ha_mode`，不依赖旧开关。

前端验证覆盖：

- 集群管理页面可选择三种模式，默认值正确。
- MySQL HA 页面正确显示模式标签和提示。
- 仅 DBMS 模式允许打开切换操作。
- 前端构建和 Vue 单文件组件编译通过。

## 非目标

- 不接入 Orchestrator API。
- 不由 DBMS 触发或代理 Orchestrator 切换。
- 不修改现有 HA 切换算法和脚本模板。
- 不改变 MySQL 拓扑、监控和域名解析算法。
- 不自动把旧的 `ha_switch_enabled=true` 集群迁移为 `dbms`。
