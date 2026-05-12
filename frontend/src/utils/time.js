export function parseBeijingTimeMs(value) {
  if (!value) {
    return NaN;
  }
  const text = String(value).trim();
  const normalized = text.includes(" ") ? text.replace(" ", "T") : text;
  const hasTimezone = /(?:Z|[+-]\d{2}:?\d{2})$/i.test(normalized);
  if (hasTimezone) {
    return new Date(normalized).getTime();
  }

  const match = normalized.match(
    /^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2})(?::(\d{2})(?:\.(\d{1,3})\d*)?)?$/,
  );
  if (!match) {
    return NaN;
  }

  const [, year, month, day, hour, minute, second = "0", millisecond = "0"] = match;
  return Date.UTC(
    Number(year),
    Number(month) - 1,
    Number(day),
    Number(hour) - 8,
    Number(minute),
    Number(second),
    Number(millisecond.padEnd(3, "0")),
  );
}

export function formatBeijingTime(value) {
  if (!value) {
    return "-";
  }
  const text = String(value).trim();
  const normalized = text.includes(" ") ? text.replace(" ", "T") : text;
  const date = new Date(parseBeijingTimeMs(normalized));
  if (Number.isNaN(date.getTime())) {
    return String(value);
  }
  return new Intl.DateTimeFormat("zh-CN", {
    timeZone: "Asia/Shanghai",
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
    hour12: false,
  }).format(date);
}
