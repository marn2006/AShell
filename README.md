# 阿里云 Workbench AI 智能终端 v1.0

基于 PRD 实现的 AI 运维终端原型，支持自然语言转 Shell 命令、预览确认、执行反馈的闭环体验。

## 功能特性

### 核心功能
- **AI/普通终端模式切换** — 一键切换，顶部按钮或 `Ctrl+Shift+I`
- **自然语言 → Shell 命令** — 支持 30+ 运维场景，中文/英文输入
- **命令预览确认** — 显示命令用途、风险等级，手动确认执行
- **高危命令拦截** — 20+ 危险模式匹配，二次确认弹窗
- **命令执行反馈** — 实时显示执行结果、耗时、成功/失败状态
- **上下文感知** — 记录当前用户、工作目录、历史指令
- **分屏 UI** — 左侧命令预览，右侧执行结果，可拖拽调整比例
- **快捷指令建议** — 10 个常用运维场景一键触发

### 支持的运维场景

| 类别 | 示例指令 | 生成命令 |
|------|----------|----------|
| 系统信息 | 查看系统信息 | `uname -a` |
| CPU/内存 | 查看CPU使用 | `top -bn1 \| head -20` |
| 磁盘管理 | 查看磁盘空间 | `df -h` |
| 网络管理 | 查看IP地址 | `ip addr show` |
| 进程管理 | 查看所有进程 | `ps aux` |
| 服务管理 | 查看运行中的服务 | `systemctl list-units` |
| 用户管理 | 查看当前用户 | `whoami` |
| 日志查看 | 查看系统日志 | `journalctl -n 50` |
| Docker | 查看Docker容器 | `docker ps -a` |
| 安全 | 查看防火墙状态 | `iptables -L -n` |

## 技术架构

```
ai-terminal/
├── app.py                  # Flask 主应用（API 路由）
├── ai_engine.py            # AI 命令引擎（自然语言解析）
├── requirements.txt        # Python 依赖
├── templates/
│   └── index.html          # 前端页面
└── static/
    ├── css/style.css       # 终端 UI 样式
    └── js/terminal.js      # 前端交互逻辑
```

### 技术栈
- **后端**: Python 3 + Flask
- **前端**: 原生 HTML/CSS/JavaScript（无框架依赖）
- **AI 引擎**: 双模式 — OpenAI API（推荐）+ 本地规则匹配（兜底）

### API 接口

| 接口 | 方法 | 说明 |
|------|------|------|
| `/` | GET | 主页面 |
| `/api/config` | GET/POST | API 配置（GET获取/POST设置） |
| `/api/parse` | POST | 自然语言解析 → 命令生成 |
| `/api/execute` | POST | 执行 Shell 命令 |
| `/api/context` | GET | 获取当前上下文 |
| `/api/suggestions` | GET | 获取快捷指令建议 |
| `/api/history` | GET | 获取执行历史 |

## 快速开始

### 安装依赖
```bash
pip install flask
```

### 启动服务
```bash
cd ai-terminal
python3 app.py
```

### 访问
浏览器打开 `http://localhost:5000`

## AI API 配置

点击页面顶部 ⚙️ 按钮打开设置面板，填入：

| 字段 | 说明 | 示例 |
|------|------|------|
| API Key | 你的 API 密钥 | `sk-xxxxxxxx` |
| Base URL | API 地址（兼容 OpenAI 格式） | 见下方 |
| Model | 模型名称 | 见下方 |

### 兼容的服务商

| 服务商 | Base URL | 推荐模型 |
|--------|----------|----------|
| OpenAI | `https://api.openai.com/v1` | gpt-3.5-turbo / gpt-4o |
| 通义千问 | `https://dashscope.aliyuncs.com/compatible-mode/v1` | qwen-turbo / qwen-plus |
| DeepSeek | `https://api.deepseek.com` | deepseek-chat |
| 智谱 GLM | `https://open.bigmodel.cn/api/paas/v4` | glm-4-flash |
| Moonshot | `https://api.moonshot.cn/v1` | moonshot-v1-8k |

> 任何兼容 OpenAI Chat Completions 接口的服务都可以接入。

### 未配置 API 时
自动使用本地规则引擎（30+ 运维场景模板），无需任何外部依赖。

## 使用说明

### AI 模式（默认）
1. 在底部输入框输入自然语言，如 `查看磁盘空间`
2. 左侧预览区显示匹配的命令和风险等级
3. 点击「执行」按钮运行命令
4. 右侧结果区显示执行输出

### 普通终端模式
1. 点击顶部「AI Agent」按钮切换为「普通终端」
2. 直接输入 Shell 命令执行

### 安全机制
- **高危命令拦截**: `rm -rf /`、格式化磁盘等危险操作自动拦截
- **二次确认**: 中高危命令执行前弹出确认弹窗
- **权限适配**: 遵循当前登录用户权限

## PRD 对照

| PRD 需求 | 实现状态 |
|----------|----------|
| AI终端模式管理 | ✅ 已实现 |
| 自然语言指令交互 | ✅ 已实现（规则匹配） |
| 命令生成与预览确认 | ✅ 已实现 |
| 命令执行与结果反馈 | ✅ 已实现 |
| 上下文感知与历史追溯 | ✅ 已实现 |
| 安全管控与权限校验 | ✅ 已实现 |
| 异常处理与容错 | ✅ 基础实现 |
| 性能（≤3秒响应） | ✅ 满足 |

## 后续规划

- [ ] 接入真实大模型 API（通义千问 / GPT）
- [ ] 多步骤任务拆解
- [ ] 常用运维模板库扩展
- [ ] WebSocket 实时终端
- [ ] 历史记录持久化
- [ ] 操作审计日志
