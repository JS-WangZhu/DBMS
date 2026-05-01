<template>
  <div ref="editorRef" class="sql-editor"></div>
</template>

<script setup>
import { autocompletion } from "@codemirror/autocomplete";
import { sql } from "@codemirror/lang-sql";
import { EditorState } from "@codemirror/state";
import { EditorView, placeholder, keymap } from "@codemirror/view";
import { basicSetup } from "codemirror";
import { onBeforeUnmount, onMounted, ref, watch } from "vue";

const props = defineProps({
  modelValue: {
    type: String,
    default: "",
  },
  placeholder: {
    type: String,
    default: "请输入 SQL",
  },
  minHeight: {
    type: Number,
    default: 260,
  },
  /**
   * 编辑器模式：sql | mongodb | redis
   */
  mode: {
    type: String,
    default: "sql",
  },
  /**
   * schema 用于自动补全：
   * - sql:      { tables: [{ name, row_count?, columns?: [{ name, data_type, comment }] }], views: [{ name }] }
   * - mongodb:  { collections: [{ name, fields?: [{ name, type }] }], views: [{ name }] }
   * - redis:    无需 schema
   */
  schema: {
    type: Object,
    default: () => ({ tables: [], views: [], collections: [] }),
  },
});

const emit = defineEmits(["update:modelValue", "run"]);

const editorRef = ref(null);
let editorView = null;

const SQL_KEYWORDS = [
  "SELECT", "FROM", "WHERE", "LIMIT", "ORDER BY", "GROUP BY", "HAVING",
  "JOIN", "LEFT JOIN", "RIGHT JOIN", "INNER JOIN", "OUTER JOIN", "ON",
  "INSERT", "INTO", "VALUES", "UPDATE", "SET", "DELETE",
  "CREATE", "ALTER", "DROP", "TABLE", "DATABASE", "INDEX", "VIEW",
  "PRIMARY KEY", "FOREIGN KEY", "DISTINCT", "UNION", "UNION ALL",
  "COUNT", "SUM", "AVG", "MIN", "MAX", "NOW", "IFNULL", "COALESCE",
  "AND", "OR", "NOT", "IN", "EXISTS", "BETWEEN", "LIKE", "IS NULL", "IS NOT NULL",
  "CASE", "WHEN", "THEN", "ELSE", "END", "DESC", "ASC", "AS",
];

const MONGO_METHODS = [
  "find", "findOne", "insertOne", "insertMany", "updateOne", "updateMany",
  "deleteOne", "deleteMany", "replaceOne", "aggregate", "count", "countDocuments",
  "estimatedDocumentCount", "distinct", "bulkWrite", "createIndex", "dropIndex",
  "getIndexes", "drop", "renameCollection", "stats", "explain", "limit", "sort",
  "skip", "project", "hint", "toArray", "pretty",
];
const MONGO_OPERATORS = [
  "$eq", "$ne", "$gt", "$gte", "$lt", "$lte", "$in", "$nin",
  "$and", "$or", "$not", "$nor", "$exists", "$type", "$regex", "$mod",
  "$all", "$elemMatch", "$size", "$set", "$unset", "$inc", "$push", "$pull",
  "$addToSet", "$pop", "$rename", "$currentDate", "$min", "$max", "$mul",
  "$match", "$group", "$project", "$sort", "$limit", "$skip", "$unwind",
  "$lookup", "$count", "$facet", "$sum", "$avg", "$first", "$last",
];
const REDIS_COMMANDS = [
  "GET", "MGET", "SET", "MSET", "SETEX", "SETNX", "DEL", "EXISTS", "KEYS",
  "SCAN", "TYPE", "TTL", "PTTL", "EXPIRE", "PEXPIRE", "PERSIST", "RENAME",
  "INCR", "DECR", "INCRBY", "DECRBY", "APPEND", "STRLEN",
  "HGET", "HMGET", "HSET", "HMSET", "HDEL", "HGETALL", "HEXISTS", "HLEN", "HKEYS", "HVALS", "HINCRBY",
  "LPUSH", "RPUSH", "LPOP", "RPOP", "LRANGE", "LLEN", "LINDEX", "LSET", "LREM", "LTRIM",
  "SADD", "SREM", "SMEMBERS", "SCARD", "SISMEMBER", "SUNION", "SINTER", "SDIFF",
  "ZADD", "ZREM", "ZRANGE", "ZREVRANGE", "ZRANGEBYSCORE", "ZRANK", "ZCARD", "ZSCORE", "ZINCRBY",
  "PING", "INFO", "DBSIZE", "SELECT", "AUTH", "CLIENT", "CONFIG", "COMMAND", "TIME",
];

// 最新 schema 通过闭包读取，保证补全能拿到实时数据
let schemaSnapshot = { tables: [], views: [], collections: [] };

function updateSchemaSnapshot(value) {
  const next = value || {};
  schemaSnapshot = {
    tables: Array.isArray(next.tables) ? next.tables : [],
    views: Array.isArray(next.views) ? next.views : [],
    collections: Array.isArray(next.collections) ? next.collections : [],
  };
}

function buildColumnIndex() {
  const map = new Map();
  for (const t of schemaSnapshot.tables || []) {
    if (!t || !t.name) continue;
    map.set(t.name.toLowerCase(), t.columns || []);
  }
  return map;
}

function collectAllColumns() {
  const seen = new Map();
  for (const t of schemaSnapshot.tables || []) {
    for (const c of t.columns || []) {
      if (!c || !c.name) continue;
      const key = c.name;
      if (!seen.has(key)) {
        seen.set(key, { column: c, tables: [t.name] });
      } else {
        seen.get(key).tables.push(t.name);
      }
    }
  }
  return Array.from(seen.values());
}

function sqlCompletions(context) {
  const text = context.state.doc.sliceString(0, context.pos);
  // 场景一：table. 语法触发字段补全
  const dotMatch = /([A-Za-z_][\w]*)\.(\w*)$/.exec(text);
  if (dotMatch) {
    const tableName = dotMatch[1];
    const typed = dotMatch[2] || "";
    const index = buildColumnIndex();
    const cols = index.get(tableName.toLowerCase()) || [];
    if (cols.length) {
      return {
        from: context.pos - typed.length,
        options: cols.map((c) => ({
          label: c.name,
          type: "property",
          detail: c.data_type || c.column_type || "",
          info: c.comment || undefined,
        })),
        validFor: /^\w*$/,
      };
    }
  }

  // 场景二：普通 token 补全（关键字 + 表名 + 字段名）
  const tokenMatch = /([A-Za-z_][\w]*)$/.exec(text);
  const from = tokenMatch ? context.pos - tokenMatch[1].length : context.pos;
  if (!tokenMatch && !context.explicit) return null;

  const options = [];
  for (const kw of SQL_KEYWORDS) {
    options.push({ label: kw, type: "keyword", boost: 1 });
  }
  for (const t of schemaSnapshot.tables || []) {
    if (!t || !t.name) continue;
    const detailParts = [];
    if (typeof t.row_count === "number" && t.row_count > 0) {
      detailParts.push(`${t.row_count} rows`);
    }
    options.push({
      label: t.name,
      type: "class",
      detail: detailParts.join(" ") || "table",
      boost: 5,
    });
  }
  for (const v of schemaSnapshot.views || []) {
    if (!v || !v.name) continue;
    options.push({ label: v.name, type: "interface", detail: "view", boost: 4 });
  }
  const columns = collectAllColumns();
  for (const item of columns) {
    const c = item.column;
    options.push({
      label: c.name,
      type: "property",
      detail: `${c.data_type || ""}${item.tables.length > 1 ? " (multi)" : ` · ${item.tables[0]}`}`,
      info: c.comment || undefined,
      boost: 3,
    });
  }
  return {
    from,
    options,
    validFor: /^\w*$/,
  };
}

function mongoCompletions(context) {
  const text = context.state.doc.sliceString(0, context.pos);
  // 场景：db.collection.<method> 补全方法
  const methodDot = /db\.([A-Za-z_][\w]*)\.(\w*)$/.exec(text);
  if (methodDot) {
    const typed = methodDot[2] || "";
    return {
      from: context.pos - typed.length,
      options: MONGO_METHODS.map((m) => ({ label: m, type: "function", detail: "method" })),
      validFor: /^\w*$/,
    };
  }
  // 场景：db. 补全集合名
  const collDot = /db\.(\w*)$/.exec(text);
  if (collDot) {
    const typed = collDot[1] || "";
    const options = [];
    for (const coll of schemaSnapshot.collections || []) {
      if (!coll || !coll.name) continue;
      options.push({ label: coll.name, type: "class", detail: "collection", boost: 5 });
    }
    for (const v of schemaSnapshot.views || []) {
      if (!v || !v.name) continue;
      options.push({ label: v.name, type: "interface", detail: "view", boost: 4 });
    }
    return {
      from: context.pos - typed.length,
      options,
      validFor: /^\w*$/,
    };
  }
  // 场景：$ 开头补全运算符
  const dollarMatch = /\$(\w*)$/.exec(text);
  if (dollarMatch) {
    const typed = dollarMatch[1] || "";
    return {
      from: context.pos - typed.length - 1,
      options: MONGO_OPERATORS.map((op) => ({ label: op, type: "keyword", detail: "operator" })),
      validFor: /^\$?\w*$/,
    };
  }
  // 默认补全：db / 集合 / 关键字
  const tokenMatch = /([A-Za-z_][\w]*)$/.exec(text);
  const from = tokenMatch ? context.pos - tokenMatch[1].length : context.pos;
  if (!tokenMatch && !context.explicit) return null;
  const options = [
    { label: "db", type: "variable", detail: "database", boost: 10 },
  ];
  for (const coll of schemaSnapshot.collections || []) {
    if (!coll || !coll.name) continue;
    options.push({ label: coll.name, type: "class", detail: "collection", boost: 5 });
  }
  for (const m of MONGO_METHODS) {
    options.push({ label: m, type: "function", detail: "method", boost: 2 });
  }
  return { from, options, validFor: /^\w*$/ };
}

function redisCompletions(context) {
  const text = context.state.doc.sliceString(0, context.pos);
  const tokenMatch = /([A-Za-z_][\w]*)$/.exec(text);
  const from = tokenMatch ? context.pos - tokenMatch[1].length : context.pos;
  if (!tokenMatch && !context.explicit) return null;
  // 仅在行首或换行后补全命令（首个 token）
  const beforeToken = text.slice(0, from);
  const isFirstToken = /(^|\n)\s*$/.test(beforeToken);
  if (!isFirstToken && !context.explicit) return null;
  return {
    from,
    options: REDIS_COMMANDS.map((cmd) => ({ label: cmd, type: "keyword", detail: "command" })),
    validFor: /^\w*$/,
  };
}

function pickCompletionFn(mode) {
  if (mode === "mongodb") return mongoCompletions;
  if (mode === "redis") return redisCompletions;
  return sqlCompletions;
}

const runKeymap = keymap.of([
  {
    key: "Ctrl-Enter",
    mac: "Cmd-Enter",
    preventDefault: true,
    run: () => {
      emit("run");
      return true;
    },
  },
]);

function createEditor() {
  if (!editorRef.value) return;
  updateSchemaSnapshot(props.schema);
  const theme = EditorView.theme({
    "&": {
      minHeight: `${props.minHeight}px`,
      border: "1px solid var(--el-border-color)",
      borderRadius: "6px",
      fontSize: "14px",
      color: "#0f172a",
      backgroundColor: "#ffffff",
      position: "relative",
    },
    ".cm-scroller": {
      fontFamily: "Consolas, 'Courier New', monospace",
      lineHeight: "1.6",
      backgroundColor: "transparent",
    },
    ".cm-content": {
      padding: "10px 12px",
      caretColor: "#0f172a",
      backgroundColor: "transparent",
    },
    ".cm-line": { backgroundColor: "transparent" },
    ".cm-selectionLayer": { zIndex: "1" },
    ".cm-selectionBackground": {
      background: "rgba(37, 99, 235, 0.3) !important",
      backgroundColor: "rgba(37, 99, 235, 0.3) !important",
    },
    "&.cm-focused .cm-selectionBackground": {
      background: "rgba(37, 99, 235, 0.45) !important",
      backgroundColor: "rgba(37, 99, 235, 0.45) !important",
    },
    "& .cm-content ::selection": {
      background: "rgba(37, 99, 235, 0.45) !important",
    },
    "&.cm-focused": { outline: "none", borderColor: "var(--el-color-primary)" },
    ".cm-activeLine": { backgroundColor: "transparent" },
    "&.cm-focused .cm-activeLine": { backgroundColor: "rgba(248, 250, 252, 0.6)" },
    ".cm-gutters": {
      backgroundColor: "transparent",
      borderRight: "1px solid #e2e8f0",
      color: "#94a3b8",
    },
    ".cm-cursor, .cm-dropCursor": { borderLeftColor: "#0f172a" },
    ".cm-placeholder": { color: "#94a3b8" },
    ".cm-tooltip": {
      backgroundColor: "#ffffff",
      border: "1px solid #dbeafe",
      color: "#0f172a",
      boxShadow: "0 6px 18px rgba(15, 23, 42, 0.08)",
    },
    ".cm-tooltip-autocomplete > ul > li[aria-selected]": {
      backgroundColor: "#dbeafe",
      color: "#1e3a8a",
    },
  });
  const langExtensions = props.mode === "sql" ? [sql()] : [];
  const completionFn = pickCompletionFn(props.mode);
  const state = EditorState.create({
    doc: props.modelValue || "",
    extensions: [
      basicSetup,
      ...langExtensions,
      placeholder(props.placeholder),
      autocompletion({
        override: [completionFn],
        activateOnTyping: true,
        closeOnBlur: true,
      }),
      runKeymap,
      theme,
      EditorView.lineWrapping,
      EditorView.updateListener.of((update) => {
        if (!update.docChanged) return;
        emit("update:modelValue", update.state.doc.toString());
      }),
    ],
  });
  editorView = new EditorView({ state, parent: editorRef.value });
}

watch(
  () => props.modelValue,
  (value) => {
    if (!editorView) return;
    const current = editorView.state.doc.toString();
    if ((value || "") === current) return;
    editorView.dispatch({
      changes: { from: 0, to: current.length, insert: value || "" },
    });
  }
);

watch(
  () => props.schema,
  (value) => {
    updateSchemaSnapshot(value);
  },
  { deep: true }
);

function insertText(text) {
  if (!editorView || !text) return;
  const sel = editorView.state.selection.main;
  editorView.dispatch({
    changes: { from: sel.from, to: sel.to, insert: text },
    selection: { anchor: sel.from + text.length },
  });
  editorView.focus();
}

defineExpose({ insertText });

onMounted(createEditor);

onBeforeUnmount(() => {
  if (editorView) {
    editorView.destroy();
    editorView = null;
  }
});
</script>

<style scoped>
.sql-editor {
  width: 100%;
}
</style>
