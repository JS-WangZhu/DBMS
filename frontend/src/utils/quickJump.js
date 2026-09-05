function menu(permission, path, label, group, pinyin, aliases = []) {
  return { permission, path, label, group, pinyin, aliases };
}

export const QUICK_JUMP_MENUS = [
  menu("dashboard", "/dashboard", "运行总览", "首页", "yun xing zong lan"),
  menu("database_apply", "/resources/database-apply", "数据库申请", "资源管理", "shu ju ku shen qing"),
  menu("database_recycle", "/resources/database-recycle", "数据库回收", "资源管理", "shu ju ku hui shou"),
  menu("application_history", "/resources/application-history", "申请流水", "资源管理", "shen qing liu shui"),
  menu("mysql_instances", "/databases/mysql/instances", "MySQL 实例管理", "服务管理 / MySQL", "mysql shi li guan li"),
  menu("mysql_instance_detail", "/databases/mysql/instance-detail", "MySQL 实例详情", "服务管理 / MySQL", "mysql shi li xiang qing"),
  menu("mysql_clusters", "/databases/mysql/clusters", "MySQL 集群管理", "服务管理 / MySQL", "mysql ji qun guan li"),
  menu("mysql_connections", "/databases/mysql/connections", "MySQL 连接管理", "服务管理 / MySQL", "mysql lian jie guan li"),
  menu("mysql_session_probe", "/databases/mysql/session-probe", "MySQL 会话探测", "服务管理 / MySQL", "mysql hui hua tan ce"),
  menu("mongodb_instances", "/databases/mongodb/instances", "MongoDB 实例管理", "服务管理 / MongoDB", "mongodb shi li guan li"),
  menu("mongodb_instance_detail", "/databases/mongodb/instance-detail", "MongoDB 实例详情", "服务管理 / MongoDB", "mongodb shi li xiang qing"),
  menu("mongodb_clusters", "/databases/mongodb/clusters", "MongoDB 集群管理", "服务管理 / MongoDB", "mongodb ji qun guan li"),
  menu("mongodb_connections", "/databases/mongodb/connections", "MongoDB 连接管理", "服务管理 / MongoDB", "mongodb lian jie guan li"),
  menu("mongodb_session_probe", "/databases/mongodb/session-probe", "MongoDB 会话探测", "服务管理 / MongoDB", "mongodb hui hua tan ce"),
  menu("redis_instances", "/databases/redis/instances", "Redis 实例管理", "服务管理 / Redis", "redis shi li guan li"),
  menu("redis_instance_detail", "/databases/redis/instance-detail", "Redis 实例详情", "服务管理 / Redis", "redis shi li xiang qing"),
  menu("redis_clusters", "/databases/redis/clusters", "Redis 集群管理", "服务管理 / Redis", "redis ji qun guan li"),
  menu("redis_connections", "/databases/redis/connections", "Redis 连接管理", "服务管理 / Redis", "redis lian jie guan li"),
  menu("postgresql_instances", "/databases/postgresql/instances", "PostgreSQL 实例管理", "服务管理 / PostgreSQL", "postgresql shi li guan li", ["pgsql", "pg"]),
  menu("postgresql_clusters", "/databases/postgresql/clusters", "PostgreSQL 集群管理", "服务管理 / PostgreSQL", "postgresql ji qun guan li", ["pgsql", "pg"]),
  menu("postgresql_session_probe", "/databases/postgresql/session-probe", "PostgreSQL 会话探测", "服务管理 / PostgreSQL", "postgresql hui hua tan ce", ["pgsql", "pg"]),
  menu("doris_instances", "/databases/doris/instances", "Doris 实例管理", "服务管理 / Doris", "doris shi li guan li"),
  menu("doris_clusters", "/databases/doris/clusters", "Doris 集群管理", "服务管理 / Doris", "doris ji qun guan li"),
  menu("diagnosis_parameter_check", "/diagnosis/parameter-check", "参数检查", "诊断调优", "can shu jian cha", ["参数采集", "parameter"]),
  menu("diagnosis_slow_query", "/diagnosis/slow-query", "慢查治理", "诊断调优", "man cha zhi li", ["慢查询", "clickhouse", "slow sql"]),
  menu("inspection_manage", "/service/inspection", "巡检状态", "巡检管理", "xun jian zhuang tai"),
  menu("inspection_param_config", "/config/inspection", "巡检参数", "巡检管理", "xun jian can shu"),
  menu("data_query", "/data-access/query", "数据查询", "数据访问", "shu ju cha xun"),
  menu("data_change", "/data-access/change", "数据变更", "数据访问", "shu ju bian geng"),
  menu("data_history", "/data-access/history", "历史记录", "数据访问", "li shi ji lu"),
  menu("data_permission_apply", "/data-access/permission-apply", "权限申请", "数据访问", "quan xian shen qing", ["生产权限申请"]),
  menu("sql_release_apply", "/data-release/apply", "SQL上线", "数据发布", "sql shang xian"),
  menu("sql_release_history", "/data-release/history", "工单历史", "数据发布", "gong dan li shi"),
  menu("data_copy_tasks", "/data-copy/tasks", "任务管理", "数据复制", "shu ju fu zhi ren wu guan li", ["canal", "mongoshake"]),
  menu("data_copy_config", "/data-copy/config", "配置中心", "数据复制", "shu ju fu zhi pei zhi zhong xin", ["kafka", "复制账号", "下游接口"]),
  menu("task_schedule", "/tasks/schedules", "调度管理", "任务管理", "diao du guan li"),
  menu("task_results", "/tasks/results", "结果查询", "任务管理", "jie guo cha xun"),
  menu("aliyun_dns_tool", "/tools/aliyun-dns", "阿里云域名工具", "快捷工具", "a li yun yu ming gong ju", ["aliyun", "dns"]),
  menu("backup_overview", "/backups/overview", "备份总览", "备份管理", "bei fen zong lan"),
  menu("backup_mysql_policies", "/backups/mysql-policies", "MySQL 策略", "备份管理 / 备份策略", "mysql ce lue"),
  menu("backup_postgresql_policies", "/backups/postgresql-policies", "PostgreSQL 策略", "备份管理 / 备份策略", "postgresql ce lue", ["pgsql", "pg"]),
  menu("backup_mongo_policies", "/backups/mongo-policies", "MongoDB 策略", "备份管理 / 备份策略", "mongodb ce lue"),
  menu("backup_records", "/backups/records", "备份记录", "备份管理", "bei fen ji lu"),
  menu("backup_tool_configs", "/backups/tool-configs", "备份工具管理", "备份管理 / 备份配置", "bei fen gong ju guan li"),
  menu("backup_s3_storage", "/backups/s3-storage", "存储配置管理", "备份管理 / 备份配置", "cun chu pei zhi guan li", ["s3"]),
  menu("backup_keys", "/backups/keys", "备份密钥管理", "备份管理 / 备份配置", "bei fen mi yao guan li"),
  menu("users_info", "/users/info", "用户信息管理", "用户管理", "yong hu xin xi guan li"),
  menu("users_role_groups", "/users/role-groups", "角色组管理", "用户管理", "jue se zu guan li"),
  menu("users_permissions", "/users/permissions", "用户权限管理", "用户管理", "yong hu quan xian guan li"),
  menu("users_data_sources", "/users/data-sources", "数据源权限管理", "用户管理", "shu ju yuan quan xian guan li"),
  menu("backup_agents", "/config/agents", "Agent 管理", "配置管理", "agent guan li"),
  menu("ai_model_config", "/config/ai-models", "AI 模型管理", "配置管理", "ai mo xing guan li"),
  menu("sql_release_config", "/config/sql-release", "数据发布配置", "配置管理", "shu ju fa bu pei zhi", ["AI预审", "工单审核"]),
  menu("ha_config", "/config/ha", "高可用配置管理", "配置管理", "gao ke yong pei zhi guan li", ["ha"]),
  menu("instance_status_config", "/config/instance-status", "实例状态检测管理", "配置管理", "shi li zhuang tai jian ce guan li"),
  menu("physical_discovery_manage", "/config/physical-discovery", "物理机探测管理", "配置管理", "wu li ji tan ce guan li"),
  menu("data_query_op_config", "/config/data-query-ops", "数据查询操作配置", "配置管理", "shu ju cha xun cao zuo pei zhi"),
  menu("backup_notify_targets", "/backups/notify-targets", "通知地址管理", "配置管理", "tong zhi di zhi guan li"),
  menu("domain_config", "/config/domain", "域名配置管理", "配置管理", "yu ming pei zhi guan li"),
  menu("mcp_platform", "/config/mcp-platform", "MCP 开放平台", "配置管理", "mcp kai fang ping tai"),
  menu("sso_config", "/config/sso", "SSO 登录管理", "配置管理", "sso deng lu guan li"),
  menu("jumpserver_config", "/config/jumpserver", "JumpServer 管理", "配置管理", "jumpserver guan li", ["堡垒机"]),
];

export function normalizeQuickJumpText(value) {
  return String(value || "").toLowerCase().replace(/[^a-z0-9\u3400-\u9fff]+/g, "");
}

function pinyinInitials(pinyin) {
  const preservedWords = /^(mysql|mongodb|redis|postgresql|doris|agent|mcp|sso|ai)$/;
  return String(pinyin || "").trim().split(/\s+/).map((part) => preservedWords.test(part) ? part : part[0] || "").join("");
}

function scoreMenu(item, query) {
  const fields = [item.label, item.pinyin, pinyinInitials(item.pinyin), ...(item.aliases || []), item.group].map(normalizeQuickJumpText);
  let best = Number.POSITIVE_INFINITY;
  fields.forEach((field, fieldIndex) => {
    const position = field.indexOf(query);
    if (position >= 0) best = Math.min(best, fieldIndex * 4 + (position === 0 ? 0 : 30 + position));
  });
  return best;
}

export function filterQuickJumpMenus(items, input, limit = 10) {
  const query = normalizeQuickJumpText(input);
  if (!query) return items.slice(0, limit);
  return items.map((item, order) => ({ item, order, score: scoreMenu(item, query) }))
    .filter((entry) => Number.isFinite(entry.score))
    .sort((a, b) => a.score - b.score || a.order - b.order)
    .slice(0, limit)
    .map((entry) => entry.item);
}
