"""Flask WebUI:在浏览器中提供 APK 与步骤选择,实时查看提取进度与日志。

用法:
    uv run python src/webui.py [--host 127.0.0.1] [--port 8000]

监听地址与端口读取 config.json 的 `webui` 段(`--host`/`--port` 可覆盖),
然后浏览器访问对应地址(默认 http://127.0.0.1:8000)。
"""
import argparse
import logging
import os
import threading

from flask import Flask, jsonify, request

import batch
import gameInformation
import phira
import resource as resource_module
from common import detect_version, list_versions, load_config
from progress import ProgressReporter

app = Flask(__name__)

STATE_LOCK = threading.Lock()
STATE = {
    "running": False,
    "done": False,
    "error": None,
    "stage": "",
    "current": 0,
    "total": 0,
    "message": "",
    "version": "",
    "logs": [],
}

PAGE = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Phigros 资源提取器</title>
<style>
  :root { color-scheme: dark; }
  body { font-family: "Segoe UI", "Microsoft YaHei", sans-serif; background: #1b1b21; color: #e0e0e6; margin: 0; padding: 24px; }
  h1 { font-size: 20px; margin: 0 0 16px; }
  .card { background: #26262e; border-radius: 10px; padding: 16px; margin-bottom: 16px; }
  label { display: block; margin: 8px 0; font-size: 14px; }
  input[type=text] { width: 100%; box-sizing: border-box; padding: 8px; margin-top: 4px; border-radius: 6px; border: 1px solid #444; background: #1b1b21; color: #eee; }
  .checks label { display: inline-block; margin-right: 16px; }
  button { background: #4a7dff; color: #fff; border: 0; border-radius: 6px; padding: 10px 22px; font-size: 15px; cursor: pointer; margin-top: 8px; }
  button:disabled { background: #444; cursor: default; }
  .bar-outer { background: #1b1b21; border-radius: 6px; height: 18px; overflow: hidden; margin: 10px 0; }
  #bar { background: linear-gradient(90deg, #4a7dff, #7aa2ff); height: 100%; width: 0; transition: width .3s; }
  #stage { font-size: 15px; font-weight: 600; }
  #count, #message { font-size: 13px; color: #9aa0b0; margin-top: 4px; }
  pre#logs { background: #111116; border-radius: 10px; padding: 12px; height: 320px; overflow: auto; font-size: 12px; line-height: 1.5; white-space: pre-wrap; }
</style>
</head>
<body>
<h1>Phigros 资源提取器 <span style="font-size:12px;color:#9aa0b0">WebUI</span></h1>
<div class="card">
  <label>APK 路径(必填,需包含版本号)
    <input type="text" id="apk" placeholder="C:\\Users\\...\\Phigros_4.0.1.apk">
  </label>
  <label>版本号(可选,留空则从文件名识别)
    <input type="text" id="version" placeholder="4.0.1">
  </label>
  <div class="checks">
    <label><input type="checkbox" id="step-info" checked> 游戏信息</label>
    <label><input type="checkbox" id="step-resource" checked> 提取资源</label>
    <label><input type="checkbox" id="step-phira" checked> Phira 打包</label>
  </div>
  <button id="start">开始</button>
  <button id="batch" style="background:#3a6b4f">批量处理 input/ 文件夹</button>
</div>
<div class="card">
  <div id="stage">空闲</div>
  <div class="bar-outer"><div id="bar"></div></div>
  <div id="count"></div>
  <div id="message"></div>
</div>
<pre id="logs"></pre>
<script>
async function refresh() {
  try {
    const s = await (await fetch('/api/status')).json();
    document.getElementById('stage').textContent = s.error ? ('出错:' + s.error) : (s.done ? '完成' : (s.stage || '空闲'));
    const total = s.total || 0, cur = s.current || 0;
    const pct = total > 0 ? Math.min(100, Math.round(cur / total * 100)) : (s.running ? 100 : 0);
    document.getElementById('bar').style.width = pct + '%';
    document.getElementById('count').textContent = total > 0 ? (cur + ' / ' + total) : (cur ? String(cur) : '');
    document.getElementById('message').textContent = s.message || '';
    const logs = document.getElementById('logs');
    logs.textContent = (s.logs || []).join('\\n');
    logs.scrollTop = logs.scrollHeight;
    document.getElementById('start').disabled = s.running;
  } catch (e) { /* 服务未就绪时忽略 */ }
}
document.getElementById('start').onclick = async () => {
  const steps = [];
  if (document.getElementById('step-info').checked) steps.push('info');
  if (document.getElementById('step-resource').checked) steps.push('resource');
  if (document.getElementById('step-phira').checked) steps.push('phira');
  const body = {
    apk: document.getElementById('apk').value,
    version: document.getElementById('version').value,
    steps: steps,
  };
  const r = await fetch('/api/run', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) });
  const j = await r.json();
  if (!j.ok) alert(j.error);
  else refresh();
};
document.getElementById('batch').onclick = async () => {
  const r = await fetch('/api/run', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ steps: ['batch'] }) });
  const j = await r.json();
  if (!j.ok) alert(j.error);
  else refresh();
};
refresh();
setInterval(refresh, 500);
</script>
</body>
</html>
"""


class StateLogHandler(logging.Handler):
    """把任务日志追加到共享状态(供前端轮询展示)。"""

    def __init__(self):
        super().__init__()
        self.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s", datefmt="%H:%M:%S"))

    def emit(self, record):
        try:
            line = self.format(record)
        except Exception:
            return
        with STATE_LOCK:
            logs = STATE["logs"]
            logs.append(line)
            if len(logs) > 300:
                del logs[:len(logs) - 300]


class WebProgress(ProgressReporter):
    """把进度事件写入共享状态。"""

    def start(self, description, total=None):
        with STATE_LOCK:
            STATE.update(stage=description, current=0, total=total or 0, message="")

    def advance(self, message=""):
        with STATE_LOCK:
            STATE["current"] += 1
            STATE["message"] = message

    def finish(self, message=""):
        with STATE_LOCK:
            STATE["stage"] = "完成"
            STATE["message"] = message or STATE["message"]


def build_task_logger():
    logger = logging.getLogger("webui.task")
    logger.setLevel(logging.INFO)
    logger.handlers.clear()
    logger.addHandler(StateLogHandler())
    logger.propagate = False
    return logger


def run_task(steps, apk_path, version):
    logger = build_task_logger()
    progress = WebProgress()
    try:
        if "batch" in steps:
            batch.process_all(("info", "resource", "phira"), load_config(), logger, progress)
        else:
            if "info" in steps:
                gameInformation.run(apk_path, version, logger, progress)
            if "resource" in steps:
                resource_module.run(apk_path, version, load_config(), logger, progress)
            if "phira" in steps:
                phira.run(version, logger, progress)
        with STATE_LOCK:
            STATE["done"] = True
    except SystemExit as e:
        with STATE_LOCK:
            STATE["error"] = str(e)
            STATE["done"] = True
    except Exception as e:
        logger.exception("任务执行出错")
        with STATE_LOCK:
            STATE["error"] = "%s: %s" % (type(e).__name__, e)
            STATE["done"] = True
    finally:
        with STATE_LOCK:
            STATE["running"] = False


@app.get("/")
def index():
    return PAGE


@app.get("/api/status")
def api_status():
    with STATE_LOCK:
        snapshot = dict(STATE)
        snapshot["logs"] = list(STATE["logs"])
    return jsonify(snapshot)


@app.post("/api/run")
def api_run():
    data = request.get_json(force=True, silent=True) or {}
    apk_path = (data.get("apk") or "").strip().strip('"')
    version = (data.get("version") or "").strip() or None
    steps = [s for s in data.get("steps", []) if s in ("info", "resource", "phira", "batch")]

    if not steps:
        return jsonify(ok=False, error="请至少选择一个步骤"), 400
    batch_mode = "batch" in steps
    needs_apk = any(s in ("info", "resource") for s in steps) and not batch_mode
    if needs_apk:
        if not apk_path or not os.path.isfile(apk_path):
            return jsonify(ok=False, error="APK 路径不存在,请检查后重试"), 400
        if version is None:
            try:
                version = detect_version(apk_path)
            except SystemExit as e:
                return jsonify(ok=False, error=str(e)), 400
    elif not batch_mode and version is None:
        versions = list_versions()
        if not versions:
            return jsonify(ok=False, error="outputs/ 下没有版本目录,请先提取"), 400
        version = versions[0]

    with STATE_LOCK:
        if STATE["running"]:
            return jsonify(ok=False, error="已有任务在运行,请等待完成"), 409
        STATE.update(
            running=True, done=False, error=None, stage="准备中",
            current=0, total=0, message="", version=version, logs=[],
        )
    threading.Thread(target=run_task, args=(steps, apk_path, version), daemon=True).start()
    return jsonify(ok=True, version=version)


def parse_args(config):
    webui = config.get("webui", {})
    parser = argparse.ArgumentParser(description="Phigros 资源提取器 WebUI")
    parser.add_argument("--host", default=webui.get("host", "127.0.0.1"),
                        help="监听地址(默认读取 config.json 的 webui.host)")
    parser.add_argument("--port", type=int, default=int(webui.get("port", 8000)),
                        help="监听端口(默认读取 config.json 的 webui.port)")
    return parser.parse_args()


def main():
    config = load_config()
    args = parse_args(config)
    print("请用浏览器访问 http://%s:%d" % (args.host, args.port))
    app.run(host=args.host, port=args.port)


if __name__ == "__main__":
    main()
