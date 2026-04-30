<template>
  <div ref="editorRef" class="sql-editor"></div>
</template>

<script setup>
import { autocompletion, completeFromList } from "@codemirror/autocomplete";
import { sql } from "@codemirror/lang-sql";
import { EditorState } from "@codemirror/state";
import { EditorView, placeholder } from "@codemirror/view";
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
});

const emit = defineEmits(["update:modelValue"]);

const editorRef = ref(null);
let editorView = null;

const sqlKeywords = [
  "SELECT",
  "FROM",
  "WHERE",
  "LIMIT",
  "ORDER BY",
  "GROUP BY",
  "HAVING",
  "JOIN",
  "LEFT JOIN",
  "RIGHT JOIN",
  "INNER JOIN",
  "OUTER JOIN",
  "ON",
  "INSERT",
  "INTO",
  "VALUES",
  "UPDATE",
  "SET",
  "DELETE",
  "CREATE",
  "ALTER",
  "DROP",
  "TABLE",
  "DATABASE",
  "INDEX",
  "VIEW",
  "PRIMARY KEY",
  "FOREIGN KEY",
  "DISTINCT",
  "UNION",
  "UNION ALL",
  "COUNT",
  "SUM",
  "AVG",
  "MIN",
  "MAX",
  "AND",
  "OR",
  "NOT",
  "IN",
  "EXISTS",
  "BETWEEN",
  "LIKE",
  "IS NULL",
  "IS NOT NULL",
  "CASE",
  "WHEN",
  "THEN",
  "ELSE",
  "END",
  "DESC",
  "ASC",
];

const completionItems = sqlKeywords.map((item) => ({
  label: item,
  type: "keyword",
}));

function createEditor() {
  if (!editorRef.value) return;
  const theme = EditorView.theme({
    "&": {
      minHeight: `${props.minHeight}px`,
      border: "1px solid var(--el-border-color)",
      borderRadius: "6px",
      fontSize: "14px",
      backgroundColor: "#ffffff",
      color: "#0f172a",
    },
    ".cm-scroller": {
      fontFamily: "Consolas, 'Courier New', monospace",
      lineHeight: "1.6",
    },
    ".cm-content": {
      padding: "10px 12px",
    },
    ".cm-selectionLayer .cm-selectionBackground": {
      backgroundColor: "rgba(37, 99, 235, 0.28) !important",
    },
    "&.cm-focused .cm-selectionLayer .cm-selectionBackground": {
      backgroundColor: "rgba(37, 99, 235, 0.38) !important",
    },
    ".cm-content ::selection, .cm-line::selection, .cm-line > span::selection, .cm-line > span > span::selection": {
      backgroundColor: "rgba(37, 99, 235, 0.38) !important",
    },
    ".cm-focused": {
      outline: "none",
      borderColor: "var(--el-color-primary)",
    },
    ".cm-activeLine": {
      backgroundColor: "#f8fafc",
    },
    ".cm-gutters": {
      backgroundColor: "#ffffff",
      borderRight: "1px solid #e2e8f0",
      color: "#94a3b8",
    },
    ".cm-cursor, .cm-dropCursor": {
      borderLeftColor: "#0f172a",
    },
    ".cm-placeholder": {
      color: "#64748b",
    },
    ".cm-tooltip": {
      backgroundColor: "#ffffff",
      border: "1px solid #dbeafe",
      color: "#0f172a",
    },
    ".cm-tooltip-autocomplete > ul > li[aria-selected]": {
      backgroundColor: "#dbeafe",
      color: "#1e3a8a",
    },
  });
  const state = EditorState.create({
    doc: props.modelValue || "",
    extensions: [
      basicSetup,
      sql(),
      placeholder(props.placeholder),
      autocompletion({
        override: [completeFromList(completionItems)],
      }),
      theme,
      EditorView.lineWrapping,
      EditorView.updateListener.of((update) => {
        if (!update.docChanged) return;
        emit("update:modelValue", update.state.doc.toString());
      }),
    ],
  });
  editorView = new EditorView({
    state,
    parent: editorRef.value,
  });
}

watch(
  () => props.modelValue,
  (value) => {
    if (!editorView) return;
    const current = editorView.state.doc.toString();
    if ((value || "") === current) return;
    editorView.dispatch({
      changes: {
        from: 0,
        to: current.length,
        insert: value || "",
      },
    });
  }
);

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
