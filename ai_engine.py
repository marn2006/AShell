"""
AI 命令引擎 - 自然语言转 Shell 命令
支持两种模式:
  1. OpenAI API 模式 - 调用大模型生成命令
  2. 本地规则模式 - 基于模板库匹配（兜底）
"""
import re
import json
from openai import OpenAI

# 全局配置
_config = {
    "api_key": "",
    "base_url": "",
    "model": "",
    "use_ai": False,
}


def update_config(api_key: str, base_url: str = "", model: str = ""):
    """更新 API 配置"""
    _config["api_key"] = api_key.strip()
    _config["base_url"] = base_url.strip() if base_url.strip() else ""
    _config["model"] = model.strip() if model.strip() else "gpt-3.5-turbo"
    _config["use_ai"] = bool(_config["api_key"])


def get_config():
    """获取配置（脱敏）"""
    key = _config["api_key"]
    masked = key[:8] + "****" + key[-4:] if len(key) > 12 else ("****" if key else "")
    return {
        "api_key_masked": masked,
        "base_url": _config["base_url"],
        "model": _config["model"],
        "use_ai": _config["use_ai"],
    }


def _get_client():
    """获取 OpenAI 客户端"""
    kwargs = {"api_key": _config["api_key"]}
    if _config["base_url"]:
        kwargs["base_url"] = _config["base_url"]
    return OpenAI(**kwargs)


SYSTEM_PROMPT = """你是一个 Linux 运维专家 AI 助手，运行在阿里云 ECS Workbench 中。
用户会用自然语言描述运维需求，你需要将其转换为可执行的 Shell 命令。

你的输出必须是严格的 JSON 格式，不要输出任何其他内容：
{
  "explanation": "对用户需求的一句话解释",
  "commands": [
    {
      "cmd": "具体shell命令",
      "desc": "这条命令的作用说明",
      "risk": "low|medium|high"
    }
  ]
}

风险等级定义:
- low: 只读查询类命令（ps, df, free, cat, grep, ip等）
- medium: 会修改系统状态但可恢复（systemctl restart, kill, mv, chmod等）
- high: 不可逆或危险操作（rm -rf, dd, mkfs, shutdown, reboot等）

规则:
1. 优先给出安全的查询/诊断命令
2. 如果用户要求修改操作，给出具体命令但标注风险
3. 高危命令必须标注为 high 风险
4. 一条自然语言可能需要多步命令，按顺序排列
5. 如果用户输入的已经是 Shell 命令，直接返回该命令
6. 如果无法理解用户意图，commands 数组留空，explanation 给出提示"""


def parse_with_openai(user_input: str) -> dict | None:
    """调用 OpenAI API 解析自然语言"""
    if not _config["use_ai"]:
        return None

    try:
        client = _get_client()
        resp = client.chat.completions.create(
            model=_config["model"],
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_input},
            ],
            temperature=0.1,
            max_tokens=1024,
        )
        content = resp.choices[0].message.content.strip()

        # 尝试提取 JSON（兼容 markdown code block）
        if "```" in content:
            match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", content, re.DOTALL)
            if match:
                content = match.group(1)

        result = json.loads(content)

        # 校验格式
        if not isinstance(result, dict) or "commands" not in result:
            return None

        # 确保每个命令有 risk 字段
        for cmd in result.get("commands", []):
            cmd.setdefault("risk", detect_risk_level(cmd.get("cmd", "")))
            cmd.setdefault("desc", "")

        return {
            "matched": len(result.get("commands", [])) > 0,
            "template_key": "AI 解析",
            "commands": result.get("commands", []),
            "explanation": result.get("explanation", "AI 已解析您的指令"),
            "risk_level": _max_risk(result.get("commands", [])),
            "is_direct": False,
            "source": "openai",
        }
    except Exception as e:
        return {
            "matched": False,
            "template_key": None,
            "commands": [],
            "explanation": f"AI 解析失败: {str(e)}，已切换到本地模式",
            "risk_level": "low",
            "is_direct": False,
            "source": "openai_error",
        }


def _max_risk(commands: list) -> str:
    """取最高风险等级"""
    order = {"low": 0, "medium": 1, "high": 2}
    max_r = "low"
    for c in commands:
        r = c.get("risk", "low")
        if order.get(r, 0) > order.get(max_r, 0):
            max_r = r
    return max_r


# ===== 本地规则引擎（兜底） =====

COMMAND_TEMPLATES = {
    "查看系统信息": {
        "commands": [
            {"cmd": "uname -a", "desc": "查看内核版本和系统架构", "risk": "low"},
            {"cmd": "cat /etc/os-release", "desc": "查看操作系统发行版信息", "risk": "low"},
        ],
        "keywords": ["系统信息", "系统版本", "操作系统", "os info", "system info", "内核版本"],
    },
    "查看系统运行时间": {
        "commands": [
            {"cmd": "uptime", "desc": "查看系统运行时间和负载", "risk": "low"},
        ],
        "keywords": ["运行时间", "uptime", "开机多久", "负载"],
    },
    "查看CPU使用情况": {
        "commands": [
            {"cmd": "top -bn1 | head -20", "desc": "查看CPU使用率和进程", "risk": "low"},
        ],
        "keywords": ["cpu", "CPU", "处理器", "cpu使用", "cpu占用"],
    },
    "查看内存使用情况": {
        "commands": [
            {"cmd": "free -h", "desc": "查看内存使用情况", "risk": "low"},
        ],
        "keywords": ["内存", "memory", "内存使用", "内存占用", "ram"],
    },
    "查看CPU占用最高的进程": {
        "commands": [
            {"cmd": "ps aux --sort=-%cpu | head -15", "desc": "按CPU使用率排序查看前15个进程", "risk": "low"},
        ],
        "keywords": ["占用cpu", "cpu最高", "cpu进程", "哪个进程占cpu"],
    },
    "查看内存占用最高的进程": {
        "commands": [
            {"cmd": "ps aux --sort=-%mem | head -15", "desc": "按内存使用率排序查看前15个进程", "risk": "low"},
        ],
        "keywords": ["占用内存", "内存最高", "内存进程", "哪个进程占内存"],
    },
    "查看磁盘空间": {
        "commands": [
            {"cmd": "df -h", "desc": "查看磁盘分区使用情况", "risk": "low"},
        ],
        "keywords": ["磁盘", "disk", "磁盘空间", "硬盘", "存储空间", "磁盘使用"],
    },
    "查看目录大小": {
        "commands": [
            {"cmd": "du -sh /* 2>/dev/null | sort -rh | head -20", "desc": "查看根目录下各文件夹大小", "risk": "low"},
        ],
        "keywords": ["目录大小", "文件夹大小", "du", "哪个目录大", "空间占用"],
    },
    "查看IP地址": {
        "commands": [
            {"cmd": "ip addr show", "desc": "查看所有网络接口和IP地址", "risk": "low"},
        ],
        "keywords": ["ip", "IP地址", "网卡", "网络接口", "ifconfig"],
    },
    "查看网络连接": {
        "commands": [
            {"cmd": "ss -tuln", "desc": "查看所有监听端口和网络连接", "risk": "low"},
        ],
        "keywords": ["端口", "网络连接", "监听端口", "开放端口", "port", "netstat"],
    },
    "查看路由表": {
        "commands": [
            {"cmd": "ip route show", "desc": "查看路由表", "risk": "low"},
        ],
        "keywords": ["路由", "route", "路由表", "网关"],
    },
    "测试网络连通性": {
        "commands": [
            {"cmd": "ping -c 4 223.5.5.5", "desc": "Ping阿里DNS测试网络连通性", "risk": "low"},
        ],
        "keywords": ["ping", "网络通不通", "网络测试", "连通性"],
    },
    "查看所有进程": {
        "commands": [
            {"cmd": "ps aux", "desc": "查看所有运行中的进程", "risk": "low"},
        ],
        "keywords": ["进程", "process", "所有进程", "进程列表", "ps"],
    },
    "查看僵尸进程": {
        "commands": [
            {"cmd": "ps aux | awk '$8 ~ /Z/ {print}'", "desc": "查找僵尸进程", "risk": "low"},
        ],
        "keywords": ["僵尸进程", "zombie"],
    },
    "查看运行中的服务": {
        "commands": [
            {"cmd": "systemctl list-units --type=service --state=running", "desc": "查看所有运行中的systemd服务", "risk": "low"},
        ],
        "keywords": ["服务", "service", "运行中的服务", "systemd"],
    },
    "查看当前用户": {
        "commands": [
            {"cmd": "whoami", "desc": "查看当前登录用户", "risk": "low"},
            {"cmd": "id", "desc": "查看当前用户的UID/GID", "risk": "low"},
        ],
        "keywords": ["当前用户", "whoami", "我是谁", "登录用户"],
    },
    "查看所有用户": {
        "commands": [
            {"cmd": "cat /etc/passwd | cut -d: -f1", "desc": "列出系统所有用户", "risk": "low"},
        ],
        "keywords": ["所有用户", "用户列表", "系统用户"],
    },
    "查看最近登录记录": {
        "commands": [
            {"cmd": "last -10", "desc": "查看最近10条登录记录", "risk": "low"},
        ],
        "keywords": ["登录记录", "登录历史", "last", "谁登录过"],
    },
    "查找大文件": {
        "commands": [
            {"cmd": "find / -type f -size +100M -exec ls -lh {} \\; 2>/dev/null | sort -k5 -rh | head -20", "desc": "查找大于100MB的文件", "risk": "low"},
        ],
        "keywords": ["大文件", "查找文件", "find", "文件太大"],
    },
    "查看当前目录": {
        "commands": [
            {"cmd": "pwd && ls -la", "desc": "查看当前目录路径和文件列表", "risk": "low"},
        ],
        "keywords": ["当前目录", "pwd", "目录内容", "ls"],
    },
    "查看系统日志": {
        "commands": [
            {"cmd": "journalctl -n 50 --no-pager", "desc": "查看最近50条系统日志", "risk": "low"},
        ],
        "keywords": ["系统日志", "日志", "log", "journalctl", "syslog"],
    },
    "查看dmesg日志": {
        "commands": [
            {"cmd": "dmesg | tail -30", "desc": "查看最近30条内核日志", "risk": "low"},
        ],
        "keywords": ["dmesg", "内核日志", "硬件日志"],
    },
    "查看防火墙状态": {
        "commands": [
            {"cmd": "iptables -L -n 2>/dev/null || echo 'iptables不可用'", "desc": "查看iptables防火墙规则", "risk": "low"},
        ],
        "keywords": ["防火墙", "firewall", "iptables", "安全组"],
    },
    "查看SELinux状态": {
        "commands": [
            {"cmd": "getenforce 2>/dev/null || echo 'SELinux不可用'", "desc": "查看SELinux状态", "risk": "low"},
        ],
        "keywords": ["selinux", "SELinux"],
    },
    "查看定时任务": {
        "commands": [
            {"cmd": "crontab -l 2>/dev/null || echo '当前用户没有定时任务'", "desc": "查看当前用户的crontab定时任务", "risk": "low"},
        ],
        "keywords": ["定时任务", "crontab", "计划任务", "cron"],
    },
    "查看Docker容器": {
        "commands": [
            {"cmd": "docker ps -a 2>/dev/null || echo 'Docker未安装'", "desc": "查看所有Docker容器", "risk": "low"},
        ],
        "keywords": ["docker", "Docker", "容器", "container"],
    },
    "查看Docker镜像": {
        "commands": [
            {"cmd": "docker images 2>/dev/null || echo 'Docker未安装'", "desc": "查看所有Docker镜像", "risk": "low"},
        ],
        "keywords": ["docker镜像", "镜像列表", "images"],
    },
    "查看已安装软件包": {
        "commands": [
            {"cmd": "rpm -qa 2>/dev/null | head -30 || dpkg -l 2>/dev/null | head -30", "desc": "查看已安装的软件包", "risk": "low"},
        ],
        "keywords": ["已安装软件", "软件包", "rpm", "dpkg", "包列表"],
    },
    "查看系统启动项": {
        "commands": [
            {"cmd": "systemctl list-unit-files --state=enabled", "desc": "查看系统启动项", "risk": "low"},
        ],
        "keywords": ["启动项", "开机启动", "enabled"],
    },
}

FUZZY_RULES = [
    (r".*查看.*系统.*信息.*|.*系统.*版本.*", "查看系统信息"),
    (r".*运行.*时间.*|.*uptime.*|.*开机.*", "查看系统运行时间"),
    (r".*cpu.*|.*CPU.*|.*处理器.*", "查看CPU使用情况"),
    (r".*内存.*|.*memory.*|.*ram.*", "查看内存使用情况"),
    (r".*磁盘.*|.*disk.*|.*硬盘.*|.*存储.*", "查看磁盘空间"),
    (r".*目录.*大小.*|.*文件夹.*大.*", "查看目录大小"),
    (r".*[Ii][Pp].*地址.*|.*网卡.*", "查看IP地址"),
    (r".*端口.*|.*port.*|.*监听.*|.*netstat.*", "查看网络连接"),
    (r".*路由.*|.*route.*|.*网关.*", "查看路由表"),
    (r".*ping.*|.*网络.*通.*|.*连通.*", "测试网络连通性"),
    (r".*进程.*|.*process.*", "查看所有进程"),
    (r".*僵尸.*|.*zombie.*", "查看僵尸进程"),
    (r".*服务.*|.*service.*|.*systemd.*", "查看运行中的服务"),
    (r".*当前.*用户.*|.*whoami.*|.*我是谁.*", "查看当前用户"),
    (r".*所有.*用户.*|.*用户.*列表.*", "查看所有用户"),
    (r".*登录.*记录.*|.*last.*|.*登录.*历史.*", "查看最近登录记录"),
    (r".*大文件.*|.*查找.*文件.*", "查找大文件"),
    (r".*当前.*目录.*|.*pwd.*|.*目录.*内容.*", "查看当前目录"),
    (r".*系统.*日志.*|.*journalctl.*", "查看系统日志"),
    (r".*dmesg.*|.*内核.*日志.*", "查看dmesg日志"),
    (r".*防火墙.*|.*firewall.*|.*iptables.*", "查看防火墙状态"),
    (r".*selinux.*|.*SELinux.*", "查看SELinux状态"),
    (r".*定时.*任务.*|.*crontab.*|.*cron.*", "查看定时任务"),
    (r".*docker.*容器.*|.*container.*", "查看Docker容器"),
    (r".*docker.*镜像.*", "查看Docker镜像"),
    (r".*已安装.*|.*软件.*包.*", "查看已安装软件包"),
    (r".*启动.*项.*|.*开机.*启动.*", "查看系统启动项"),
]

DANGEROUS_COMMANDS = [
    r"rm\s+-rf\s+/",
    r"rm\s+-rf\s+\*",
    r"mkfs\.",
    r"dd\s+if=.*of=/dev/",
    r">\s*/dev/sd",
    r"chmod\s+.*777.*/",
    r":\(\)\s*\{.*\}",
    r"curl.*\|\s*sh",
    r"wget.*\|\s*sh",
    r"echo.*>\s*/etc/",
    r"userdel\s+root",
    r"passwd\s+root",
    r"shutdown",
    r"reboot",
    r"init\s+0",
    r"halt",
    r"poweroff",
    r"killall",
    r"pkill\s+-9",
]


def detect_risk_level(command: str) -> str:
    """检测命令风险等级"""
    cmd_lower = command.strip().lower()
    for pattern in DANGEROUS_COMMANDS:
        if re.search(pattern, cmd_lower):
            return "high"
    medium_patterns = [
        r"^systemctl\s+(stop|restart|disable)",
        r"^kill\s+", r"^yum\s+(remove|erase)",
        r"^apt\s+remove", r"^rm\s+", r"^mv\s+",
        r"^chmod\s+", r"^chown\s+",
    ]
    for pattern in medium_patterns:
        if re.search(pattern, cmd_lower):
            return "medium"
    return "low"


def parse_local(user_input: str) -> dict:
    """本地规则解析（兜底）"""
    text = user_input.strip()

    # 直接命令检测
    shell_prefixes = [
        "ls", "cd", "cat", "grep", "find", "ps", "top", "df", "du",
        "free", "ip", "ss", "netstat", "systemctl", "journalctl",
        "dmesg", "crontab", "docker", "yum", "apt", "pip", "npm",
        "chmod", "chown", "rm", "mv", "cp", "mkdir", "tar", "wget",
        "curl", "ssh", "scp", "ping", "traceroute", "iptables",
        "useradd", "userdel", "passwd", "mount", "fdisk", "kill",
        "tail", "head", "awk", "sed", "sort", "uniq", "wc", "echo",
    ]
    first_word = text.split()[0] if text.split() else ""
    if first_word in shell_prefixes:
        risk = detect_risk_level(text)
        return {
            "matched": True,
            "template_key": "直接执行",
            "commands": [{"cmd": text, "desc": "用户直接输入的Shell命令", "risk": risk}],
            "explanation": "检测到Shell命令，直接执行",
            "risk_level": risk,
            "is_direct": True,
            "source": "local",
        }

    # 精确匹配
    for key, template in COMMAND_TEMPLATES.items():
        for kw in template["keywords"]:
            if kw in text:
                risk = max(
                    (c["risk"] for c in template["commands"]),
                    key=lambda r: {"low": 0, "medium": 1, "high": 2}[r],
                )
                return {
                    "matched": True,
                    "template_key": key,
                    "commands": template["commands"],
                    "explanation": f"已为您匹配到「{key}」相关命令",
                    "risk_level": risk,
                    "is_direct": False,
                    "source": "local",
                }

    # 模糊匹配
    for pattern, key in FUZZY_RULES:
        if re.match(pattern, text, re.IGNORECASE):
            template = COMMAND_TEMPLATES[key]
            risk = max(
                (c["risk"] for c in template["commands"]),
                key=lambda r: {"low": 0, "medium": 1, "high": 2}[r],
            )
            return {
                "matched": True,
                "template_key": key,
                "commands": template["commands"],
                "explanation": f"根据您的描述，匹配到「{key}」",
                "risk_level": risk,
                "is_direct": False,
                "source": "local",
            }

    return {
        "matched": False,
        "template_key": None,
        "commands": [],
        "explanation": "抱歉，暂未识别您的意图。请尝试更具体的描述，或直接输入Shell命令。",
        "risk_level": "low",
        "is_direct": False,
        "source": "local",
    }


def parse_natural_language(user_input: str) -> dict:
    """
    统一入口：优先用 OpenAI，失败/未配置时回退到本地规则
    """
    # 如果配置了 AI，先尝试 OpenAI
    if _config["use_ai"]:
        result = parse_with_openai(user_input)
        if result and result.get("matched"):
            return result
        # AI 失败，回退本地
        if result and result.get("source") == "openai_error":
            local_result = parse_local(user_input)
            local_result["ai_fallback"] = result.get("explanation", "")
            return local_result

    return parse_local(user_input)


def get_risk_badge(risk: str) -> str:
    badges = {"low": "🟢 低风险", "medium": "🟡 中风险", "high": "🔴 高风险"}
    return badges.get(risk, "⚪ 未知")


def get_suggestions() -> list:
    return [
        "查看磁盘空间", "查看内存使用", "查看CPU使用",
        "查看IP地址", "查看端口监听", "查看运行中的服务",
        "查看当前用户", "查找大文件", "查看系统日志",
        "查看Docker容器",
    ]
