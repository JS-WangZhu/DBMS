const DB_TYPE_LABELS = {
  mysql: "MySQL",
  mongodb: "MongoDB",
  redis: "Redis",
  postgresql: "PostgreSQL",
  doris: "Doris",
};

export function dbTypeDisplayName(value) {
  return DB_TYPE_LABELS[value] || value || "-";
}

export function buildClusterLabel(item, dbTypeSelected) {
  const name = item?.cluster_name || "-";
  return dbTypeSelected ? name : `${name} [${dbTypeDisplayName(item?.db_type)}]`;
}

export function filterClusterOptions(items, filters = {}) {
  return (items || []).filter((item) => {
    const matchesBusiness =
      !filters.business ||
      (filters.business === "__unset__"
        ? !item.business_line
        : item.business_line === filters.business);
    const matchesDbType = !filters.dbType || item.db_type === filters.dbType;
    const matchesResult = !filters.result || item.backup_status === filters.result;
    return matchesBusiness && matchesDbType && matchesResult;
  });
}
