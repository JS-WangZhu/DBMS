const MENU_PERMISSION_STRUCTURE = [
  { key: "dashboard_group", label: "运行总览", children: ["dashboard"] },
  { key: "resource_management", label: "资源管理", children: ["database_apply", "database_recycle", "application_history"] },
  { key: "service_manage", label: "服务管理", children: [
    { key: "mysql", label: "MySQL", children: ["mysql_instances", "mysql_instance_detail", "mysql_clusters", "mysql_connections", "mysql_session_probe"] },
    { key: "mongodb", label: "MongoDB", children: ["mongodb_instances", "mongodb_instance_detail", "mongodb_clusters", "mongodb_connections", "mongodb_session_probe"] },
    { key: "redis", label: "Redis", children: ["redis_instances", "redis_instance_detail", "redis_clusters", "redis_connections"] },
    { key: "postgresql", label: "PostgreSQL", children: ["postgresql_instances", "postgresql_clusters", "postgresql_session_probe"] },
    { key: "doris", label: "Doris", children: ["doris_instances", "doris_clusters"] },
  ] },
  { key: "diagnosis_tuning", label: "诊断调优", children: ["diagnosis_parameter_check", "diagnosis_slow_query"] },
  { key: "inspection", label: "巡检管理", children: ["inspection_manage", "inspection_param_config"] },
  { key: "data_access", label: "数据访问", children: ["data_query", "data_change", "data_history", "data_permission_apply"] },
  { key: "data_release", label: "数据发布", children: ["sql_release_apply", "sql_release_history"] },
  { key: "data_copy", label: "数据复制", children: ["data_copy_tasks", "data_copy_config"] },
  { key: "task_management", label: "任务管理", children: ["task_schedule", "task_results"] },
  { key: "quick_tools", label: "快捷工具", children: ["aliyun_dns_tool"] },
  { key: "backup", label: "备份管理", children: [
    "backup_overview",
    { key: "backup_policies", label: "策略管理", children: ["backup_mysql_policies", "backup_postgresql_policies", "backup_mongo_policies"] },
    "backup_records",
    { key: "backup_config", label: "备份配置", children: ["backup_tool_configs", "backup_s3_storage", "backup_keys"] },
  ] },
  { key: "config", label: "配置管理", children: [
    "backup_agents",
    "ai_model_config",
    "sql_release_config",
    "ha_config",
    "instance_status_config",
    "physical_discovery_manage",
    "data_query_op_config",
    "backup_notify_targets",
    "domain_config",
    "mcp_platform",
    "sso_config",
    "jumpserver_config",
  ] },
  { key: "users", label: "用户管理", children: ["users_info", "users_permissions", "users_role_groups", "users_data_sources"] },
];

export function buildMenuPermissionTree(catalog, { disabled = false, disabledKeys = [] } = {}) {
  const disabledKeySet = new Set(disabledKeys || []);
  const leafMap = new Map(
    (catalog || []).map((item) => [item.key, {
      key: item.key,
      label: item.label,
      disabled: disabled || disabledKeySet.has(item.key),
      inherited: disabledKeySet.has(item.key),
    }]),
  );
  const usedKeys = new Set();

  function convert(node) {
    if (typeof node === "string") {
      const leaf = leafMap.get(node) || null;
      if (leaf) usedKeys.add(node);
      return leaf;
    }
    const children = (node.children || []).map(convert).filter(Boolean);
    if (!children.length) return null;
    return { key: node.key, label: node.label, disabled, children };
  }

  const nodes = MENU_PERMISSION_STRUCTURE.map(convert).filter(Boolean);
  const uncategorized = [...leafMap.values()].filter((item) => !usedKeys.has(item.key));
  if (uncategorized.length) {
    nodes.push({ key: "uncategorized", label: "其他菜单", disabled, children: uncategorized });
  }
  return { nodes, leafKeys: [...leafMap.keys()] };
}
