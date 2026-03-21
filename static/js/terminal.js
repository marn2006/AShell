/**
 * 阿里云 Workbench AI 终端 - 前端交互逻辑
 */

let aiMode = true;
let pendingDangerCommand = null;
let isExecuting = false;

// ===== 初始化 =====
document.addEventListener("DOMContentLoaded", () => {
    loadSuggestions();
    loadContext();
    loadConfig();
    setupKeyboard();
    setupResizer();
});

// ===== 快捷建议 =====
async function loadSuggestions() {
    try {
        const res = await fetch("/api/suggestions");
        const suggestions = await res.json();
        const container = document.getElementById("quickSuggestions");
        container.innerHTML = suggestions
            .map(s => `<div class="suggestion-chip" onclick="useSuggestion('${s}')">${s}</div>`)
            .join("");
    } catch (e) {
        console.error("加载建议失败:", e);
    }
}

function useSuggestion(text) {
    document.getElementById("userInput").value = text;
    handleSend();
}

// ===== 上下文 =====
async function loadContext() {
    try {
        const res = await fetch("/api/context");
        const ctx = await res.json();
        document.getElementById("currentUser").textContent = ctx.user;
        document.getElementById("instanceName").textContent = ctx.hostname;
        document.getElementById("currentCwd").textContent = ctx.cwd;
    } catch (e) {
        console.error("加载上下文失败:", e);
    }
}

// ===== 键盘事件 =====
function setupKeyboard() {
    const input = document.getElementById("userInput");
    input.addEventListener("keydown", (e) => {
        if (e.key === "Enter" && !e.shiftKey) {
            e.preventDefault();
            handleSend();
        }
    });

    // Ctrl+Shift+I 切换AI模式
    document.addEventListener("keydown", (e) => {
        if (e.ctrlKey && e.shiftKey && e.key === "I") {
            e.preventDefault();
            toggleAiMode();
        }
    });
}

// ===== AI模式切换 =====
function toggleAiMode() {
    aiMode = !aiMode;
    const btn = document.getElementById("aiToggle");
    const text = document.getElementById("aiToggleText");
    const badge = btn.querySelector(".toggle-badge");
    const container = document.querySelector(".main-container");
    const prompt = document.getElementById("promptPrefix");

    if (aiMode) {
        btn.classList.add("active");
        text.textContent = "AI Agent";
        badge.textContent = "ON";
        container.classList.remove("ai-off");
        prompt.textContent = "Agent >";
        document.getElementById("userInput").placeholder =
            "请输入自然语言指令或Shell命令（如：查看磁盘空间）";
    } else {
        btn.classList.remove("active");
        text.textContent = "普通终端";
        badge.textContent = "OFF";
        container.classList.add("ai-off");
        prompt.textContent = "root@ecs:~$";
        document.getElementById("userInput").placeholder =
            "请输入Shell命令（如：ls -la）";
    }
}

// ===== 发送指令 =====
async function handleSend() {
    const input = document.getElementById("userInput");
    const text = input.value.trim();
    if (!text || isExecuting) return;

    input.value = "";
    isExecuting = true;
    document.getElementById("sendBtn").disabled = true;

    if (aiMode) {
        await handleAiCommand(text);
    } else {
        await executeDirectCommand(text);
    }

    isExecuting = false;
    document.getElementById("sendBtn").disabled = false;
    input.focus();
    loadContext();
}

// ===== AI模式处理 =====
async function handleAiCommand(text) {
    // 显示加载状态
    showPreviewLoading(text);

    try {
        const res = await fetch("/api/parse", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ input: text }),
        });
        const result = await res.json();
        renderPreview(result);
    } catch (e) {
        showPreviewError("解析失败: " + e.message);
    }
}

// ===== 直接命令模式 =====
async function executeDirectCommand(text) {
    addExecutionBlock("direct", text, "running");
    const result = await executeCommand(text);
    updateExecutionBlock("direct", result);
}

// ===== 预览渲染 =====
function showPreviewLoading(text) {
    const empty = document.getElementById("emptyPreview");
    const preview = document.getElementById("commandPreview");
    empty.style.display = "none";
    preview.style.display = "block";
    preview.innerHTML = `
        <div class="parse-info">
            <span class="parse-info-icon">🤔</span>
            <span class="parse-info-text">正在解析: <strong>${escapeHtml(text)}</strong></span>
            <span class="loading-dots"></span>
        </div>
    `;
}

function renderPreview(result) {
    const preview = document.getElementById("commandPreview");

    if (!result.matched) {
        // 如果有 AI 回退信息，显示它
        const fallbackNote = result.ai_fallback ? `<div class="no-match-hint" style="margin-top:8px;color:var(--accent-yellow);">⚠️ ${escapeHtml(result.ai_fallback)}</div>` : "";
        preview.innerHTML = `
            <div class="no-match-card">
                <div class="no-match-icon">🤷</div>
                <div class="no-match-text">${escapeHtml(result.explanation)}</div>
                <div class="no-match-hint">试试："查看磁盘空间"、"查看内存"、"查看IP地址"<br>或直接输入 Shell 命令</div>
                ${fallbackNote}
            </div>
        `;
        return;
    }

    const riskClass = `risk-${result.risk_level}`;
    const riskBadge = result.risk_badge;
    const sourceLabel = result.source === "openai" ? "🧠 AI" : "📐 本地规则";

    let commandsHtml = result.commands
        .map(
            (cmd, i) => `
        <div class="command-card">
            <div class="command-card-header">
                <span class="command-step">步骤 ${i + 1}</span>
                <span class="command-desc">${escapeHtml(cmd.desc)}</span>
                <span class="command-risk-tag ${riskClass}">${getRiskText(cmd.risk)}</span>
            </div>
            <div class="command-body">
                <div class="command-code">${escapeHtml(cmd.cmd)}</div>
            </div>
            <div class="command-actions">
                <button class="btn btn-copy" onclick="copyCommand('${escapeAttr(cmd.cmd)}')">📋 复制</button>
                <button class="btn btn-execute ${cmd.risk === "high" ? "btn-danger-exe" : ""}" 
                        onclick="handleExecute('${escapeAttr(cmd.cmd)}', '${cmd.risk}')">
                    ▶ 执行
                </button>
            </div>
        </div>
    `
        )
        .join("");

    preview.innerHTML = `
        <div class="parse-info">
            <span class="parse-info-icon">✅</span>
            <span class="parse-info-text">${escapeHtml(result.explanation)}</span>
            <span class="source-badge">${sourceLabel}</span>
            <span class="risk-badge ${riskClass}">${riskBadge}</span>
        </div>
        ${commandsHtml}
    `;
}

function showPreviewError(msg) {
    const preview = document.getElementById("commandPreview");
    preview.innerHTML = `
        <div class="no-match-card">
            <div class="no-match-icon">❌</div>
            <div class="no-match-text">${escapeHtml(msg)}</div>
        </div>
    `;
}

// ===== 命令执行 =====
function handleExecute(command, risk) {
    if (risk === "high") {
        pendingDangerCommand = command;
        document.getElementById("dangerCommand").textContent = command;
        document.getElementById("dangerModal").style.display = "flex";
    } else {
        runExecute(command);
    }
}

function cancelDanger() {
    document.getElementById("dangerModal").style.display = "none";
    pendingDangerCommand = null;
}

function confirmDanger() {
    document.getElementById("dangerModal").style.display = "none";
    if (pendingDangerCommand) {
        runExecute(pendingDangerCommand);
        pendingDangerCommand = null;
    }
}

async function runExecute(command) {
    const blockId = "exec_" + Date.now();
    addExecutionBlock(blockId, command, "running");

    const result = await executeCommand(command);
    updateExecutionBlock(blockId, result);
}

async function executeCommand(command) {
    try {
        const res = await fetch("/api/execute", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ command }),
        });
        return await res.json();
    } catch (e) {
        return { success: false, output: "", error: "请求失败: " + e.message, blocked: false };
    }
}

// ===== 执行结果渲染 =====
function addExecutionBlock(id, command, status) {
    const container = document.getElementById("executionResults");
    const block = document.createElement("div");
    block.className = "execution-block";
    block.id = id;
    block.innerHTML = `
        <div class="execution-header">
            <span class="exec-status ${status}">${getStatusText(status)}</span>
            <span class="exec-command">$ ${escapeHtml(command)}</span>
            <span class="exec-time">${getTimeStr()}</span>
        </div>
        <div class="execution-output">
            <span class="loading-dots">执行中</span>
        </div>
    `;
    container.appendChild(block);
    scrollToBottom();
}

function updateExecutionBlock(id, result) {
    const block = document.getElementById(id);
    if (!block) return;

    const statusEl = block.querySelector(".exec-status");
    const outputEl = block.querySelector(".execution-output");
    const timeEl = block.querySelector(".exec-time");

    if (result.blocked) {
        statusEl.className = "exec-status blocked";
        statusEl.textContent = "⛔ 已拦截";
        outputEl.className = "execution-output execution-blocked";
        outputEl.textContent = result.error;
    } else if (result.success) {
        statusEl.className = "exec-status success";
        statusEl.textContent = "✅ 成功";
        outputEl.className = "execution-output";
        outputEl.textContent = result.output || "(无输出)";
    } else {
        statusEl.className = "exec-status failed";
        statusEl.textContent = "❌ 失败";
        outputEl.className = "execution-output execution-error";
        outputEl.textContent = (result.output || "") + (result.error ? "\n" + result.error : "");
    }

    if (result.elapsed) {
        timeEl.textContent = `${result.elapsed}s`;
    }

    scrollToBottom();
}

function clearResult() {
    document.getElementById("executionResults").innerHTML = "";
}

// ===== 工具函数 =====
function getStatusText(status) {
    const map = { running: "⏳ 执行中", success: "✅ 成功", failed: "❌ 失败", blocked: "⛔ 已拦截" };
    return map[status] || status;
}

function getRiskText(risk) {
    const map = { low: "🟢 低风险", medium: "🟡 中风险", high: "🔴 高风险" };
    return map[risk] || "⚪ 未知";
}

function getTimeStr() {
    const now = new Date();
    return now.toTimeString().slice(0, 8);
}

function escapeHtml(str) {
    const div = document.createElement("div");
    div.textContent = str;
    return div.innerHTML;
}

function escapeAttr(str) {
    return str.replace(/'/g, "\\'").replace(/"/g, "&quot;");
}

function copyCommand(cmd) {
    navigator.clipboard.writeText(cmd).then(() => {
        // 简单反馈
        const btn = event.target;
        const orig = btn.textContent;
        btn.textContent = "✅ 已复制";
        setTimeout(() => (btn.textContent = orig), 1500);
    });
}

function scrollToBottom() {
    const body = document.getElementById("resultBody");
    requestAnimationFrame(() => {
        body.scrollTop = body.scrollHeight;
    });
}

// ===== API 设置 =====
async function loadConfig() {
    try {
        const res = await fetch("/api/config");
        const cfg = await res.json();
        if (cfg.use_ai) {
            document.getElementById("apiKeyInput").value = "";
            document.getElementById("baseUrlInput").value = cfg.base_url || "";
            document.getElementById("modelInput").value = cfg.model || "";
            showConfigStatus(`当前已连接 AI（Key: ${cfg.api_key_masked}，模型: ${cfg.model}）`, "info");
        }
    } catch (e) {
        console.error("加载配置失败:", e);
    }
}

function openSettings() {
    document.getElementById("settingsModal").style.display = "flex";
    loadConfigDetail();
}

function closeSettings() {
    document.getElementById("settingsModal").style.display = "none";
}

async function loadConfigDetail() {
    try {
        const res = await fetch("/api/config");
        const cfg = await res.json();
        document.getElementById("baseUrlInput").value = cfg.base_url || "";
        document.getElementById("modelInput").value = cfg.model || "";
        if (cfg.use_ai) {
            showConfigStatus(`✅ 当前已连接 AI（Key: ${cfg.api_key_masked}，模型: ${cfg.model}）`, "info");
        } else {
            showConfigStatus("ℹ️ 未配置 API，当前使用本地规则模式", "info");
        }
    } catch (e) {}
}

async function saveSettings() {
    const apiKey = document.getElementById("apiKeyInput").value;
    const baseUrl = document.getElementById("baseUrlInput").value;
    const model = document.getElementById("modelInput").value;

    try {
        const res = await fetch("/api/config", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ api_key: apiKey, base_url: baseUrl, model: model }),
        });
        const result = await res.json();
        if (result.ok) {
            showConfigStatus("✅ 配置已保存", "success");
            setTimeout(() => closeSettings(), 1000);
        } else {
            showConfigStatus("❌ 保存失败", "error");
        }
    } catch (e) {
        showConfigStatus("❌ 请求失败: " + e.message, "error");
    }
}

function showConfigStatus(msg, type) {
    const el = document.getElementById("configStatus");
    el.textContent = msg;
    el.className = "form-status " + type;
}

// ===== 分隔条拖拽 =====
function setupResizer() {
    const resizer = document.getElementById("resizer");
    const preview = document.getElementById("previewPanel");
    const container = document.querySelector(".main-container");
    let isResizing = false;

    resizer.addEventListener("mousedown", (e) => {
        isResizing = true;
        document.body.style.cursor = "col-resize";
        document.body.style.userSelect = "none";
    });

    document.addEventListener("mousemove", (e) => {
        if (!isResizing) return;
        const containerRect = container.getBoundingClientRect();
        const newWidth = e.clientX - containerRect.left;
        const pct = (newWidth / containerRect.width) * 100;
        if (pct >= 20 && pct <= 70) {
            preview.style.flex = `0 0 ${pct}%`;
        }
    });

    document.addEventListener("mouseup", () => {
        isResizing = false;
        document.body.style.cursor = "";
        document.body.style.userSelect = "";
    });
}
