export function getInstanceStatusExportColumns(dbType, helpers = {}) {
  if (dbType === "mysql") {
    return [
      ["应用连接", (row) => helpers.appConnText(row)],
      ["只读状态", (row) => helpers.readonlyText(helpers.mysqlStatus(row).effective_read_only)],
      ["主从角色", (row) => helpers.roleText(helpers.mysqlRole(row))],
      ["复制延迟", (row) => (helpers.shouldHideReplicationDetails(row) ? "-" : (helpers.mysqlStatus(row).seconds_behind_master ?? "-"))],
      ["I/O线程", (row) => (helpers.shouldHideReplicationDetails(row) ? "-" : helpers.threadLabel(helpers.mysqlStatus(row).replica_io_running, "I/O"))],
      ["SQL线程", (row) => (helpers.shouldHideReplicationDetails(row) ? "-" : helpers.threadLabel(helpers.mysqlStatus(row).replica_sql_running, "SQL"))],
    ];
  }
  if (dbType === "mongodb") {
    return [["主从角色", (row) => helpers.mongoRoleText(helpers.mongoRole(row))]];
  }
  if (dbType === "redis") {
    return [
      ["主从角色", (row) => helpers.redisRoleText(helpers.redisRole(row))],
      ["高可用模式", (row) => helpers.redisHaModeText(helpers.redisHaMode(row))],
      ["复制源信息", (row) => helpers.redisReplicationSource(row)],
      ["实例内存使用率", (row) => helpers.redisContainerMemoryText(row)],
    ];
  }
  if (dbType === "postgresql") {
    return [
      ["主从角色", (row) => helpers.postgresqlRoleText(helpers.postgresqlPayload(row).replication_role)],
      ["连接使用率", (row) => helpers.postgresqlConnectionUsageText(row)],
    ];
  }
  return [];
}
