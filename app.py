"""
阿里云 Workbench AI 终端 - Flask 后端
"""
import json
import subprocess
import time
from datetime import datetime
from flask import Flask, render_template, request, jsonify
from ai_engine import parse_natural_language, get_risk_badge, get_suggestions, detect_risk_level, update_config, get_config

app = Flask(__name__)

# 会话上下文
session_context = {
    "user": "root",
    "hostname": "ecs-workbench",
    "cwd": "/root",
    "history": [],
}


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/context")
def get_context():
    return jsonify(session_context)


@app.route("/api/suggestions")
def suggestions():
    return jsonify(get_suggestions())


@app.route("/api/config", methods=["GET"])
def api_get_config():
    """获取当前配置（脱敏）"""
    return jsonify(get_config())


@app.route("/api/config", methods=["POST"])
def api_set_config():
    """设置 API 配置"""
    data = request.json
    api_key = data.get("api_key", "")
    base_url = data.get("base_url", "")
    model = data.get("model", "")

    update_config(api_key, base_url, model)

    return jsonify({"ok": True, "config": get_config()})


@app.route("/api/parse", methods=["POST"])
def parse_command():
    """自然语言 → 命令解析"""
    data = request.json
    user_input = data.get("input", "").strip()
    if not user_input:
        return jsonify({"error": "输入不能为空"}), 400

    result = parse_natural_language(user_input)
    result["risk_badge"] = get_risk_badge(result["risk_level"])

    # 记录历史
    session_context["history"].append({
        "time": datetime.now().strftime("%H:%M:%S"),
        "input": user_input,
        "commands": [c["cmd"] for c in result.get("commands", [])],
        "risk": result["risk_level"],
    })
    if len(session_context["history"]) > 100:
        session_context["history"] = session_context["history"][-100:]

    return jsonify(result)


@app.route("/api/execute", methods=["POST"])
def execute_command():
    """执行 Shell 命令"""
    data = request.json
    command = data.get("command", "").strip()
    if not command:
        return jsonify({"error": "命令不能为空"}), 400

    # 安全检查
    risk = detect_risk_level(command)
    if risk == "high":
        return jsonify({
            "success": False,
            "output": "",
            "error": f"⛔ 高危命令已被拦截: {command}\n此命令可能对系统造成不可逆损害。",
            "risk": "high",
            "blocked": True,
        })

    start_time = time.time()
    try:
        result = subprocess.run(
            command,
            shell=True,
            capture_output=True,
            text=True,
            timeout=30,
            cwd=session_context["cwd"],
        )
        elapsed = round(time.time() - start_time, 2)

        output = result.stdout or ""
        error = result.stderr or ""
        success = result.returncode == 0

        # 更新上下文（cd 命令）
        if command.strip().startswith("cd "):
            new_dir = command.strip()[3:].strip()
            if new_dir == "~" or new_dir == "":
                session_context["cwd"] = "/root"
            elif new_dir.startswith("/"):
                session_context["cwd"] = new_dir
            else:
                import os
                session_context["cwd"] = os.path.normpath(
                    os.path.join(session_context["cwd"], new_dir)
                )

        return jsonify({
            "success": success,
            "output": output,
            "error": error,
            "returncode": result.returncode,
            "elapsed": elapsed,
            "risk": risk,
            "blocked": False,
        })
    except subprocess.TimeoutExpired:
        return jsonify({
            "success": False,
            "output": "",
            "error": "命令执行超时（30秒）",
            "risk": risk,
            "blocked": False,
        })
    except Exception as e:
        return jsonify({
            "success": False,
            "output": "",
            "error": f"执行异常: {str(e)}",
            "risk": risk,
            "blocked": False,
        })


@app.route("/api/history")
def get_history():
    return jsonify(session_context["history"][-50:])


@app.route("/api/clear_history", methods=["POST"])
def clear_history():
    session_context["history"] = []
    return jsonify({"ok": True})


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
