function stripSqlStringsAndComments(sql) {
  const source = String(sql || "");
  let output = "";
  let quote = "";
  let escaped = false;
  let lineComment = false;
  let blockComment = false;
  for (let index = 0; index < source.length; index += 1) {
    const char = source[index];
    const next = source[index + 1] || "";
    if (lineComment) {
      if (char === "\n") { lineComment = false; output += "\n"; } else output += " ";
      continue;
    }
    if (blockComment) {
      if (char === "*" && next === "/") { blockComment = false; output += "  "; index += 1; } else output += char === "\n" ? "\n" : " ";
      continue;
    }
    if (quote) {
      output += " ";
      if (escaped) escaped = false;
      else if (char === "\\") escaped = true;
      else if (char === quote) quote = "";
      continue;
    }
    if (char === "-" && next === "-") { lineComment = true; output += "  "; index += 1; continue; }
    if (char === "#") { lineComment = true; output += " "; continue; }
    if (char === "/" && next === "*") { blockComment = true; output += "  "; index += 1; continue; }
    if (char === "'" || char === '"') { quote = char; output += " "; continue; }
    output += char;
  }
  return output;
}

function normalizeTableReference(reference) {
  const parts = String(reference || "").split(".");
  return String(parts[parts.length - 1] || "").trim().replace(/^`|`$/g, "").toLowerCase();
}

export function extractSqlTableNames(sql) {
  const source = stripSqlStringsAndComments(sql);
  const identifier = "(?:`[^`]+`|[A-Za-z_][A-Za-z0-9_$]*)(?:\\.(?:`[^`]+`|[A-Za-z_][A-Za-z0-9_$]*))?";
  const patterns = [
    new RegExp(`\\b(?:UPDATE|DELETE\\s+FROM|INSERT\\s+(?:IGNORE\\s+)?INTO|REPLACE\\s+INTO|FROM|JOIN|ALTER\\s+TABLE|TRUNCATE\\s+TABLE)\\s+(${identifier})`, "gi"),
    new RegExp(`\\b(?:CREATE|DROP)\\s+TABLE\\s+(?:IF\\s+(?:NOT\\s+)?EXISTS\\s+)?(${identifier})`, "gi"),
  ];
  const names = new Set();
  patterns.forEach((pattern) => {
    for (const match of source.matchAll(pattern)) {
      const name = normalizeTableReference(match[1]);
      if (name) names.add(name);
    }
  });
  return names;
}

export function extractReleaseObjectNames(content, dbType = "mysql") {
  if (dbType !== "mongodb") return extractSqlTableNames(content);
  const names = new Set();
  const original = String(content || "");
  const source = original.replace(/(['"])(?:\\.|(?!\1).)*\1/gs, " ");
  for (const match of source.matchAll(/\bdb\.([A-Za-z_][\w$]*)\s*\./g)) {
    names.add(match[1].toLowerCase());
  }
  for (const match of original.matchAll(/\bgetCollection\s*\(\s*['"]([^'"]+)['"]\s*\)/gi)) {
    names.add(match[1].toLowerCase());
  }
  return names;
}
