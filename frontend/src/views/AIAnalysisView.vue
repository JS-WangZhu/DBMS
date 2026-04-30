<template>
  <div class="page">
    <el-card>
      <template #header>
        <span>智能 SQL 分析</span>
      </template>

      <el-form :model="form" label-position="left">
        <el-row :gutter="15">
          <el-col :span="4">
            <el-form-item label="类型" label-width="40px">
              <el-select v-model="form.db_type" placeholder="类型" @change="onTypeChange">
                <el-option label="MySQL" value="mysql" />
                <el-option label="MongoDB" value="mongodb" />
              </el-select>
            </el-form-item>
          </el-col>
          <el-col :span="4">
            <el-form-item label="项目" label-width="40px">
              <el-select v-model="form.business_line" placeholder="项目" @change="onScopeChange">
                <el-option v-for="bl in businessLines" :key="bl" :label="bl" :value="bl" />
              </el-select>
            </el-form-item>
          </el-col>
          <el-col :span="4">
            <el-form-item label="环境" label-width="40px">
              <el-select v-model="form.environment" placeholder="环境" @change="onScopeChange">
                <el-option v-for="env in environments" :key="env" :label="env" :value="env" />
              </el-select>
            </el-form-item>
          </el-col>
          <el-col :span="5">
            <el-form-item label="集群" label-width="40px">
              <el-select v-model="form.cluster_id" placeholder="选择集群" @change="onClusterChange">
                <el-option v-for="c in clusters" :key="c.id" :label="c.name" :value="c.id" />
              </el-select>
            </el-form-item>
          </el-col>
          <el-col :span="5">
            <el-form-item label="库名" label-width="40px">
              <el-select v-model="form.database" filterable placeholder="选择库名">
                <el-option v-for="db in databases" :key="db" :label="db" :value="db" />
              </el-select>
            </el-form-item>
          </el-col>
          <el-col :span="2">
            <el-button type="primary" :loading="analyzing" @click="startAnalysis" style="width: 100%">智能分析</el-button>
          </el-col>
        </el-row>

        <el-form-item label="待分析 SQL" label-width="85px">
          <el-input
            v-model="form.statement"
            type="textarea"
            :rows="4"
            placeholder="请输入待分析的 SQL 或命令，多条请换行..."
          />
        </el-form-item>
      </el-form>

      <div v-if="analyzing || analysisResult" class="result-area">
        <div class="result-header">
          <div class="status-badge-container" v-if="analysisResult">
            <el-tag v-if="analysisResult.includes('[建议放行]')" type="success" effect="dark" class="status-badge">
              <el-icon><Check /></el-icon> 建议放行
            </el-tag>
            <el-tag v-else-if="analysisResult.includes('[不建议放行]')" type="danger" effect="dark" class="status-badge">
              <el-icon><Close /></el-icon> 不建议放行
            </el-tag>
          </div>
          <el-button link type="primary" @click="copyResult">复制结果</el-button>
        </div>
        <el-card ref="resultCardRef" shadow="never" class="analysis-card">
          <div v-if="analyzing && !analysisResult" class="loading-placeholder">
            AI 正在深度思考中，请稍候...
          </div>
          <div class="markdown-content" v-html="renderMarkdown(analysisResult)"></div>
        </el-card>
      </div>
    </el-card>
  </div>
</template>

<script setup>
import { onMounted, ref, reactive, nextTick, watch } from "vue";
import { ElMessage } from "element-plus";
import { Check, Close } from "@element-plus/icons-vue";
import { listClusters as listAllowedClusters } from "../api/modules/clusters";
import { performAIAnalysis } from "../api/modules/ai";
import { listMysqlDatabases, listMongoDatabases } from "../api/modules/data_access";

const form = reactive({
  db_type: "mysql",
  business_line: "",
  environment: "",
  cluster_id: null,
  database: "",
  statement: "",
});

const businessLines = ref([]);
const environments = ref([]);
const clusters = ref([]);
const databases = ref([]);
const allClusters = ref([]);
const analyzing = ref(false);
const analysisResult = ref("");
const resultCardRef = ref(null);

// 监听结果变化，自动滚动到底部
watch(analysisResult, () => {
  if (analyzing.value && resultCardRef.value) {
    nextTick(() => {
      const el = resultCardRef.value.$el.querySelector('.el-card__body');
      if (el) {
        el.scrollTop = el.scrollHeight;
      }
    });
  }
});

// 简易 Markdown 渲染（处理标题、代码块、表格、加粗、处理 think 标签、列表、状态标签）
function renderMarkdown(text) {
  if (!text) return "";
  
  let html = text;

  // 1. 处理 <think> 标签：输出时显示，输出完隐藏（折叠）
  if (html.includes('<think>')) {
    if (html.includes('</think>')) {
      // 输出完毕，使用折叠框并默认关闭
      html = html.replace(/<think>([\s\S]*?)<\/think>/g, (match, content) => {
        return `<details class="think-details"><summary>AI 思考过程 (已完成)</summary><div class="think-content">${content}</div></details>`;
      });
    } else {
      // 正在输出中，使用折叠框并默认展开
      const parts = html.split('<think>');
      const beforeThink = parts[0];
      const thinking = parts[1] || "";
      html = `${beforeThink}<details open class="think-details thinking"><summary>AI 正在思考...</summary><div class="think-content">${thinking}</div></details>`;
    }
  }

  // 基础转义
  html = html
    .replace(/&/g, "&amp;")
    .replace(/</g, (match, offset) => {
      // 保护我们刚刚生成的 HTML 标签
      const sub = html.substring(offset);
      if (sub.startsWith('</details>') || sub.startsWith('<details') || sub.startsWith('<summary') || sub.startsWith('</summary') || sub.startsWith('<div class="think-content"') || sub.startsWith('</div>')) {
        return match;
      }
      return "&lt;";
    })
    .replace(/>/g, (match, offset) => {
      const prev = html.substring(0, offset + 1);
      if (prev.endsWith('</details>') || prev.endsWith('>') || prev.endsWith('</summary>') || prev.endsWith('</div>')) {
        return match;
      }
      return "&gt;";
    });

  // 代码块
  html = html.replace(/```(\w*)\n([\s\S]*?)```/g, '<pre class="code-block"><code>$2</code></pre>');
  
  // 行内代码
  html = html.replace(/`([^`]+)`/g, "<code>$1</code>");
  
  // 标题
  html = html.replace(/^### (.*$)/gm, "<h4>$1</h4>");
  html = html.replace(/^## (.*$)/gm, "<h3>$1</h3>");
  html = html.replace(/^# (.*$)/gm, "<h2>$1</h2>");
  
  // 加粗
  html = html.replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>");
  
  // 列表处理
   // 无序列表：先替换每行，然后将连续的 li 包裹在 ul 中
   html = html.replace(/^\s*[-*+]\s+(.*)$/gm, "<li>$1</li>");
   html = html.replace(/(<li>.*<\/li>)/gs, (match) => {
     // 避免重复包裹
     if (match.includes('<ul>')) return match;
     return `<ul>${match}</ul>`;
   });
   
   // 有序列表
   html = html.replace(/^\s*(\d+)\.\s+(.*)$/gm, "<li data-index=\"$1\">$2</li>");
   html = html.replace(/(<li data-index=.*<\/li>)/gs, (match) => {
     if (match.includes('<ol>')) return match;
     return `<ol>${match}</ol>`;
   });
  
  // 状态标签着色
  html = html.replace(/\[可执行\]/g, '<span class="status-tag status-success">[可执行]</span>');
  html = html.replace(/\[建议放行\]/g, '<span class="status-tag status-success">[建议放行]</span>');
  html = html.replace(/\[有风险\]/g, '<span class="status-tag status-warning">[有风险]</span>');
  html = html.replace(/\[语法错误\]/g, '<span class="status-tag status-danger">[语法错误]</span>');
  html = html.replace(/\[禁止执行\]/g, '<span class="status-tag status-danger">[禁止执行]</span>');
  html = html.replace(/\[不建议放行\]/g, '<span class="status-tag status-danger">[不建议放行]</span>');

  // 换行（非列表、非表格、非代码块内部）
  html = html.replace(/\n/g, "<br>");
  
  // 简单的表格处理
  const lines = html.split("<br>");
  let inTable = false;
  let tableHtml = "";
  const newLines = [];
  
  for (let line of lines) {
    if (line.trim().startsWith("|") && line.includes("|")) {
      if (!inTable) {
        inTable = true;
        tableHtml = '<table class="md-table">';
      }
      if (line.includes("---")) continue;
      
      const cells = line.split("|").filter(c => c.trim() !== "");
      tableHtml += "<tr>" + cells.map(c => `<td>${c.trim()}</td>`).join("") + "</tr>";
    } else {
      if (inTable) {
        inTable = false;
        tableHtml += "</table>";
        newLines.push(tableHtml);
      }
      newLines.push(line);
    }
  }
  if (inTable) newLines.push(tableHtml + "</table>");
  
  return newLines.join("");
}

function copyResult() {
  if (!analysisResult.value) return;
  
  // 过滤掉 think 标签后再复制，或者保留原样？通常用户希望复制最终结果
  // 这里我们保留原样，但处理下兼容性
  const text = analysisResult.value;
  
  if (navigator.clipboard && window.isSecureContext) {
    navigator.clipboard.writeText(text).then(() => {
      ElMessage.success("已复制到剪贴板");
    }).catch(() => {
      fallbackCopyText(text);
    });
  } else {
    fallbackCopyText(text);
  }
}

function fallbackCopyText(text) {
  const textArea = document.createElement("textarea");
  textArea.value = text;
  textArea.style.position = "fixed";
  textArea.style.left = "-9999px";
  textArea.style.top = "0";
  document.body.appendChild(textArea);
  textArea.focus();
  textArea.select();
  try {
    document.execCommand('copy');
    ElMessage.success("已复制到剪贴板");
  } catch (err) {
    ElMessage.error("复制失败，请手动选择复制");
  }
  document.body.removeChild(textArea);
}

async function loadClusters() {
  try {
    const { data } = await listAllowedClusters(form.db_type);
    allClusters.value = data?.data || [];
    businessLines.value = [...new Set(allClusters.value.map(c => c.business_line))];
    environments.value = [...new Set(allClusters.value.map(c => c.environment))];
    filterClusters();
  } catch (error) {
    ElMessage.error("获取集群列表失败");
  }
}

function filterClusters() {
  clusters.value = allClusters.value.filter(c => {
    return (!form.business_line || c.business_line === form.business_line) &&
           (!form.environment || c.environment === form.environment);
  });
}

function onTypeChange() {
  form.cluster_id = null;
  form.database = "";
  loadClusters();
}

function onScopeChange() {
  form.cluster_id = null;
  filterClusters();
}

async function onClusterChange() {
  form.database = "";
  if (!form.cluster_id) return;
  try {
    const fetcher = form.db_type === "mysql" ? listMysqlDatabases : listMongoDatabases;
    const { data } = await fetcher(form.cluster_id);
    databases.value = data?.data?.databases || [];
  } catch (error) {
    ElMessage.error("获取数据库列表失败");
  }
}

async function startAnalysis() {
  if (!form.cluster_id || !form.database || !form.statement) {
    return ElMessage.warning("请完善分析参数");
  }
  analyzing.value = true;
  analysisResult.value = "";
  
  let contentText = "";
  
  try {
    const token = localStorage.getItem("dbms_token");
    const response = await fetch("/api/v1/ai/analyze/stream", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "Authorization": `Bearer ${token}`
      },
      body: JSON.stringify(form)
    });

    if (!response.ok) {
      const err = await response.json();
      throw new Error(err.message || "请求失败");
    }

    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let buffer = "";

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;

      buffer += decoder.decode(value, { stream: true });
      const lines = buffer.split("\n");
      
      // 最后一行可能不完整，保留到下一次处理
      buffer = lines.pop() || "";

      for (const line of lines) {
        const trimmedLine = line.trim();
        if (trimmedLine.startsWith("data: ")) {
          try {
            const data = JSON.parse(trimmedLine.slice(6));
            if (data.error) {
              ElMessage.error(data.error);
              break;
            }
            if (data.content) {
              contentText += data.content;
            }
            
            analysisResult.value = contentText;
          } catch (e) {
            // 解析失败忽略
          }
        }
      }
    }
  } catch (error) {
    ElMessage.error(error.message || "分析请求失败");
  } finally {
    analyzing.value = false;
  }
}

onMounted(loadClusters);
</script>

<style scoped>
.page { padding: 20px; }
.result-area { margin-top: 10px; }
.result-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 5px; }
.status-badge-container { display: flex; align-items: center; }
.status-badge { font-size: 16px; padding: 15px 20px; border-radius: 8px; font-weight: bold; }
.status-badge .el-icon { margin-right: 5px; vertical-align: middle; }
.analysis-card :deep(.el-card__body) {
  height: 500px;
  overflow-y: auto;
  background: #ffffff;
  border: 1px solid #d0d7de;
  border-radius: 6px;
}
.loading-placeholder { padding: 20px; color: #909399; font-style: italic; }
.markdown-content {
  line-height: 1.6;
  color: #1f2328;
  font-size: 14px;
  padding: 16px 32px;
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", "Noto Sans", Helvetica, Arial, sans-serif, "Apple Color Emoji", "Segoe UI Emoji";
}
.markdown-content h2 {
  padding-bottom: .3em;
  font-size: 1.5em;
  border-bottom: 1px solid #d0d7de;
  margin-top: 24px;
  margin-bottom: 16px;
  font-weight: 600;
}
.markdown-content h3 {
  font-size: 1.25em;
  margin-top: 24px;
  margin-bottom: 16px;
  font-weight: 600;
}
.markdown-content h4 {
  font-size: 1em;
  margin-top: 24px;
  margin-bottom: 16px;
  font-weight: 600;
}
.code-block {
  padding: 16px;
  overflow: auto;
  font-size: 85%;
  line-height: 1.45;
  color: #1f2328;
  background-color: #f6f8fa;
  border-radius: 6px;
  margin-top: 0;
  margin-bottom: 16px;
}
.code-block code {
  background: transparent;
  padding: 0;
  color: inherit;
  font-family: ui-monospace, SFMono-Regular, SF Mono, Menlo, Consolas, Liberation Mono, monospace;
}
code {
  padding: .2em .4em;
  margin: 0;
  font-size: 85%;
  white-space: break-spaces;
  background-color: rgba(175, 184, 193, 0.2);
  border-radius: 6px;
  font-family: ui-monospace, SFMono-Regular, SF Mono, Menlo, Consolas, Liberation Mono, monospace;
}
.md-table {
  border-spacing: 0;
  border-collapse: collapse;
  margin-top: 0;
  margin-bottom: 16px;
  width: max-content;
  max-width: 100%;
  overflow: auto;
}
.md-table td {
  padding: 6px 13px;
  border: 1px solid #d0d7de;
}
.md-table tr {
  background-color: #ffffff;
  border-top: 1px solid #d8dee4;
}
.md-table tr:nth-child(even) {
  background-color: #f6f8fa;
}
.md-table tr:hover { background-color: #e9e9e9; }

/* Think details 样式 */
.think-details {
  margin: 10px 0;
  border: 1px solid #e4e7ed;
  border-radius: 4px;
  background: #fdfdfd;
}
.think-details summary {
  padding: 8px 12px;
  cursor: pointer;
  color: #909399;
  font-size: 13px;
  background: #f5f7fa;
  border-radius: 4px;
  outline: none;
}
.think-details.thinking summary {
  color: #409eff;
}
.think-content {
  padding: 12px;
  font-size: 13px;
  color: #606266;
  font-style: italic;
  white-space: pre-wrap;
}

/* 状态标签样式 */
.status-tag {
  display: inline-block;
  padding: 0 8px;
  height: 24px;
  line-height: 22px;
  font-size: 12px;
  border-radius: 4px;
  border: 1px solid;
  margin: 0 4px;
  font-weight: bold;
}
.status-success {
  background-color: #f0f9eb;
  border-color: #e1f3d8;
  color: #67c23a;
}
.status-warning {
  background-color: #fdf6ec;
  border-color: #faecd8;
  color: #e6a23c;
}
.status-danger {
  background-color: #fef0f0;
  border-color: #fde2e2;
  color: #f56c6c;
}

/* 列表样式 */
.markdown-content ul {
  padding-left: 20px;
  margin: 10px 0;
}
.markdown-content li {
  margin-bottom: 4px;
}
</style>
