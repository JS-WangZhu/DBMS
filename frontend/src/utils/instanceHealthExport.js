export async function fetchHealthForAllRows(rows, fetchBatch, batchSize = 200) {
  const ids = rows
    .map((row) => row?.id)
    .filter((id) => id !== null && id !== undefined);
  const size = Math.max(1, Number(batchSize) || 200);
  const healthById = {};
  for (let offset = 0; offset < ids.length; offset += size) {
    Object.assign(healthById, await fetchBatch(ids.slice(offset, offset + size)) || {});
  }
  return healthById;
}
