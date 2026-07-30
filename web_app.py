#!/usr/bin/env python3
"""无需 Tk 的本地浏览器界面，避免旧版 macOS Tcl/Tk 崩溃。"""
import json
import threading
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs
from urllib.parse import urlsplit

from src.models import RunOptions
from src.pipeline import SubtitlePipeline, parse_urls
from src.session_login import login_with_qr


PROJECT_DIR = Path(__file__).resolve().parent
DEFAULT_OUTPUT = PROJECT_DIR / "outputs"
SESSION_FILE = PROJECT_DIR / ".private" / "douyin_cookie.txt"
LIVE_LOG = PROJECT_DIR / "outputs" / "实时运行日志.txt"
STATE = {"running": False, "login_running": False, "logs": [], "result": "", "error": ""}
LOCK = threading.Lock()


def append_log(message):
    with LOCK:
        STATE["logs"].append(message)
        STATE["logs"] = STATE["logs"][-400:]
        LIVE_LOG.parent.mkdir(parents=True, exist_ok=True)
        with LIVE_LOG.open("a", encoding="utf-8") as stream:
            stream.write(str(message) + "\n")


def reset_live_log(output_dir):
    global LIVE_LOG
    LIVE_LOG = output_dir / "实时运行日志.txt"
    LIVE_LOG.parent.mkdir(parents=True, exist_ok=True)
    LIVE_LOG.write_text("", encoding="utf-8")


def save_local_cookie(value):
    """保存用户在本机页面粘贴的会话信息，绝不写入日志或响应内容。"""
    cookie = str(value or "").strip()
    if not cookie:
        raise ValueError("Cookie 内容不能为空。")
    SESSION_FILE.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    SESSION_FILE.write_text(cookie, encoding="utf-8")
    SESSION_FILE.chmod(0o600)


def page() -> str:
    default_output = str(DEFAULT_OUTPUT)
    return f"""<!doctype html><html lang='zh-CN'><head><meta charset='utf-8'>
<meta name='viewport' content='width=device-width,initial-scale=1'>
<title>抖音作者主页字幕批量提取</title><style>
body{{margin:0;background:#f6f8fb;color:#1e293b;font-family:-apple-system,BlinkMacSystemFont,"PingFang SC",sans-serif}}
main{{max-width:900px;margin:32px auto;padding:0 20px}} h1{{font-size:25px;margin:0 0 8px}}
.note{{color:#64748b;margin:0 0 22px}} .card{{background:#fff;border:1px solid #e2e8f0;border-radius:12px;padding:20px;margin-top:16px}}
label{{display:block;font-weight:600;margin:13px 0 6px}} textarea,input,select{{box-sizing:border-box;width:100%;border:1px solid #cbd5e1;border-radius:7px;padding:10px;font:14px inherit}}
textarea{{height:150px;resize:vertical}} .grid{{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:0 18px}} .checks{{display:flex;gap:20px;margin-top:14px}}
.checks label{{font-weight:400}} .checks input{{width:auto;margin-right:6px}} button{{margin-top:20px;background:#1664d9;color:#fff;border:0;border-radius:7px;padding:11px 22px;font:15px inherit;cursor:pointer}}
button:disabled{{background:#94a3b8;cursor:wait}} pre{{white-space:pre-wrap;word-break:break-word;min-height:190px;margin:0;background:#0f172a;color:#dbeafe;padding:14px;border-radius:8px;font:13px/1.55 ui-monospace,Menlo,monospace}}
.result{{margin-top:12px;font-weight:600}} .warn{{font-size:13px;color:#92400e;background:#fffbeb;padding:10px;border-radius:7px;margin-top:14px}}
</style></head><body><main><h1>抖音作者主页字幕批量提取</h1><p class='note'>本页面只运行在你的电脑上（127.0.0.1），关闭启动用的终端即可停止服务。</p>
<form id='form' class='card'><label>作者主页链接（一行一个）</label><textarea name='urls' placeholder='https://www.douyin.com/user/...'></textarea>
<div class='grid'><div><label>输出目录</label><input name='output' value='{default_output}'></div><div><label>转写模型</label><select name='model'><option value='base'>base（更快）</option><option value='small' selected>small（推荐）</option><option value='medium'>medium（更准确）</option></select></div>
<div><label>语言</label><select name='language'><option value='zh' selected>中文</option><option value='auto'>自动识别</option><option value='en'>英语</option></select></div></div>
<div class='checks'><label><input type='checkbox' name='gpu'>使用 GPU</label><label><input type='checkbox' name='keep_audio' checked>保留下载的音频</label><label><input type='checkbox' name='cleanup_source_videos' checked>完成后清理原视频</label></div>
<div class='warn'>请只处理你有权下载和使用的视频内容。Cookie 仅供主页采集器的本机任务使用。</div><button id='run'>开始执行</button></form>
<section class='card'><label>抖音登录（可选）</label><button type='button' id='qrLogin'>打开扫码登录窗口</button><p class='note'>扫码后只保存本机浏览器会话，不显示或导出 Cookie。首次使用请先双击 安装全部组件.command。</p><label>手动保存 Cookie（备用）</label><input id='cookieHeader' type='password' autocomplete='off' placeholder='仅在本机粘贴；不会显示、上传或写入日志'><button type='button' id='saveCookie'>仅保存到本机</button></section>
<section class='card'><label>运行日志</label><pre id='logs'>等待开始…</pre><div class='result' id='result'></div></section></main>
<script>const form=document.querySelector('#form'),run=document.querySelector('#run'),logs=document.querySelector('#logs'),result=document.querySelector('#result'),saveCookie=document.querySelector('#saveCookie'),cookieHeader=document.querySelector('#cookieHeader'),qrLogin=document.querySelector('#qrLogin');
form.addEventListener('submit',async e=>{{e.preventDefault();const d=new FormData(form);const p=Object.fromEntries(d.entries());p.gpu=d.has('gpu');p.keep_audio=d.has('keep_audio');p.cleanup_source_videos=d.has('cleanup_source_videos');const r=await fetch('/api/start',{{method:'POST',headers:{{'Content-Type':'application/json'}},body:JSON.stringify(p)}});const j=await r.json();if(j.error)alert(j.error);}});
saveCookie.addEventListener('click',async()=>{{const r=await fetch('/api/session',{{method:'POST',headers:{{'Content-Type':'application/json'}},body:JSON.stringify({{cookie:cookieHeader.value}})}});const j=await r.json();if(j.error){{alert(j.error);return;}}cookieHeader.value='';alert('已仅保存到本机。');}});
qrLogin.addEventListener('click',async()=>{{const r=await fetch('/api/login',{{method:'POST'}});const j=await r.json();if(j.error)alert(j.error);}});
async function refresh(){{const s=await (await fetch('/api/status')).json();logs.textContent=s.logs.join('\\n')||'等待开始…';result.textContent=s.error?('错误：'+s.error):(s.result?'完成：'+s.result:'');run.disabled=s.running||s.login_running;run.textContent=s.running?'正在执行…':'开始执行';qrLogin.disabled=s.running||s.login_running;qrLogin.textContent=s.login_running?'等待扫码登录…':'打开扫码登录窗口';}}setInterval(refresh,900);refresh();</script></body></html>"""


def start_job(payload):
    urls = parse_urls(str(payload.get("urls", "")))
    if not urls:
        raise ValueError("请至少输入一个作者主页链接。")
    output_dir = Path(str(payload.get("output") or DEFAULT_OUTPUT)).expanduser()
    with LOCK:
        if STATE["running"]:
            raise RuntimeError("已有任务正在运行。")
        reset_live_log(output_dir)
        STATE.update({"running": True, "logs": ["已开始任务…"], "result": "", "error": ""})
    append_log("已开始任务…")

    def work():
        try:
            options = RunOptions(
                output_dir=output_dir,
                model=str(payload.get("model") or "small"),
                language=None if payload.get("language") == "auto" else str(payload.get("language") or "zh"),
                use_gpu=bool(payload.get("gpu")),
                keep_audio=bool(payload.get("keep_audio", True)),
                cleanup_source_videos=bool(payload.get("cleanup_source_videos", True)),
            )
            result = SubtitlePipeline(options, append_log).run(urls)
            with LOCK:
                STATE["result"] = str(result)
        except Exception as exc:
            append_log(f"执行失败：{exc}")
            with LOCK:
                STATE["error"] = str(exc)
        finally:
            with LOCK:
                STATE["running"] = False

    threading.Thread(target=work, daemon=True).start()


def start_qr_login():
    with LOCK:
        if STATE["running"] or STATE["login_running"]:
            raise RuntimeError("当前已有任务正在运行。")
        STATE["login_running"] = True
        STATE["error"] = ""

    def work():
        try:
            login_with_qr(append_log)
        except Exception as exc:
            append_log(f"扫码登录失败：{exc}")
            with LOCK:
                STATE["error"] = str(exc)
        finally:
            with LOCK:
                STATE["login_running"] = False

    threading.Thread(target=work, daemon=True).start()


class Handler(BaseHTTPRequestHandler):
    def log_message(self, _format, *_args):
        return

    def send_json(self, data, status=200):
        body = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        route = urlsplit(self.path).path
        if route == "/api/status":
            with LOCK:
                self.send_json(dict(STATE))
            return
        if route == "/favicon.ico":
            self.send_response(204)
            self.end_headers()
            return
        if route in ("/", "/index.html"):
            body = page().encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        self.send_error(404)

    def do_POST(self):
        route = urlsplit(self.path).path
        if route not in ("/api/start", "/api/session", "/api/login"):
            self.send_error(404)
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
            payload = json.loads(self.rfile.read(length).decode("utf-8")) if length else {}
            if route == "/api/session":
                save_local_cookie(payload.get("cookie"))
            elif route == "/api/login":
                start_qr_login()
            else:
                start_job(payload)
            self.send_json({"ok": True})
        except Exception as exc:
            self.send_json({"error": str(exc)}, 400)


if __name__ == "__main__":
    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    address = f"http://127.0.0.1:{server.server_port}/"
    print(f"已启动本地界面：{address}")
    print("关闭此终端即可停止服务。")
    threading.Timer(0.5, lambda: webbrowser.open(address)).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
