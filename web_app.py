#!/usr/bin/env python3
# -*- coding: utf-8 -*-
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
STRATEGIES = {
    "speed": {"model": "base", "audio_workers": 4, "transcription_workers": 2, "beam_size": 1},
    "balanced": {"model": "small", "audio_workers": 3, "transcription_workers": 1, "beam_size": 3},
    "quality": {"model": "medium", "audio_workers": 2, "transcription_workers": 1, "beam_size": 5},
}


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


def legacy_page() -> str:
    default_output = str(DEFAULT_OUTPUT)
    return f"""<!doctype html><html lang='zh-CN'><head><meta charset='utf-8'>
<meta name='viewport' content='width=device-width,initial-scale=1'>
<title>字幕工作台 · 抖音作者批量提取</title><style>
:root{{--ink:#14213d;--muted:#64748b;--line:#e4e9f2;--violet:#6558e8;--blue:#2375e1;--mint:#18b58e;--surface:rgba(255,255,255,.94)}}
*{{box-sizing:border-box}} body{{margin:0;color:var(--ink);font-family:-apple-system,BlinkMacSystemFont,"PingFang SC","Microsoft YaHei",sans-serif;background:radial-gradient(circle at 8% -12%,#d6e8ff 0,transparent 30rem),radial-gradient(circle at 96% 3%,#ede1ff 0,transparent 26rem),#f5f7fb}}
main{{max-width:1120px;margin:0 auto;padding:34px 22px 56px}} .hero{{display:flex;align-items:end;justify-content:space-between;gap:24px;margin:10px 0 26px}} .eyebrow{{display:inline-flex;align-items:center;gap:7px;color:#4f46c5;font-size:12px;font-weight:800;letter-spacing:.08em;text-transform:uppercase}} .eyebrow i{{width:8px;height:8px;border-radius:50%;background:var(--mint);box-shadow:0 0 0 5px #d9f8ee}} h1{{font-size:clamp(28px,4vw,42px);letter-spacing:-.045em;margin:10px 0 8px}} .sub{{max-width:620px;margin:0;color:var(--muted);line-height:1.7}} .local{{padding:10px 13px;border:1px solid #d8dcff;border-radius:999px;background:#fff;color:#554ac5;font-size:13px;white-space:nowrap}}
.layout{{display:grid;grid-template-columns:minmax(0,1.42fr) minmax(290px,.78fr);gap:18px}} .card{{background:var(--surface);border:1px solid rgba(218,225,237,.9);box-shadow:0 16px 42px rgba(33,50,86,.08);border-radius:20px;padding:22px}} .card+ .card{{margin-top:18px}} .section-title{{display:flex;justify-content:space-between;align-items:baseline;gap:14px;margin-bottom:4px;font-size:16px;font-weight:800}} .hint{{color:var(--muted);font-size:12px;font-weight:500}}
label{{display:block;margin:15px 0 7px;font-size:13px;font-weight:750}} textarea,input,select{{width:100%;border:1px solid #d8e0ec;border-radius:11px;background:#fbfcfe;color:var(--ink);padding:11px 12px;font:14px inherit;outline:none;transition:.18s}} textarea:focus,input:focus,select:focus{{border-color:#857cf0;box-shadow:0 0 0 4px #eeedff;background:#fff}} textarea{{height:145px;resize:vertical;line-height:1.55}} .field-grid{{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:0 13px}}
.preset-row{{display:grid;grid-template-columns:repeat(3,1fr);gap:8px;margin-top:14px}} .preset{{margin:0;padding:10px 8px;border:1px solid #e0e4f4;border-radius:12px;background:#fff;color:#536178;text-align:left;cursor:pointer;font:inherit;transition:.18s}} .preset strong,.preset span{{display:block}} .preset strong{{font-size:13px;color:var(--ink)}} .preset span{{margin-top:3px;font-size:11px;line-height:1.35}} .preset:hover,.preset.active{{border-color:#8178ee;background:#f4f2ff;transform:translateY(-1px)}}
.checks{{display:grid;gap:9px;margin-top:17px}} .check{{display:flex;align-items:center;gap:9px;margin:0;padding:9px 10px;border-radius:10px;background:#f8faff;color:#3b4b66;font-size:13px;font-weight:600}} .check input{{width:16px;height:16px;accent-color:var(--violet)}} .notice{{margin-top:15px;padding:11px 12px;border-radius:12px;background:#fff7e8;color:#865b19;font-size:12px;line-height:1.55}} .primary{{display:inline-flex;align-items:center;justify-content:center;gap:9px;width:100%;margin-top:18px;border:0;border-radius:12px;padding:13px 18px;background:linear-gradient(135deg,var(--violet),var(--blue));box-shadow:0 10px 20px rgba(76,86,211,.25);color:#fff;font:700 15px inherit;cursor:pointer;transition:.18s}} .primary:hover{{transform:translateY(-1px);filter:brightness(1.04)}} .primary:disabled{{background:#9aa7bc;box-shadow:none;cursor:wait;transform:none}}
.status-top{{display:flex;align-items:center;justify-content:space-between;gap:12px}} .status-dot{{display:inline-flex;align-items:center;gap:7px;color:#42516a;font-size:13px;font-weight:700}} .status-dot:before{{content:"";width:8px;height:8px;border-radius:99px;background:#94a3b8}} .status-dot.live:before{{background:var(--mint);box-shadow:0 0 0 5px #d9f8ee}} .progress{{height:8px;margin:18px 0 9px;overflow:hidden;border-radius:99px;background:#edf1f7}} .progress i{{display:block;width:0;height:100%;border-radius:inherit;background:linear-gradient(90deg,#18b58e,#4b82f6);transition:width .35s ease}} .progress-copy{{color:var(--muted);font-size:12px}} .stat-grid{{display:grid;grid-template-columns:repeat(2,1fr);gap:9px;margin-top:20px}} .stat{{padding:12px;border:1px solid #ebeff6;border-radius:13px;background:#fff}} .stat b{{display:block;font-size:19px}} .stat span{{display:block;margin-top:3px;color:var(--muted);font-size:11px}}
pre{{min-height:280px;max-height:470px;overflow:auto;margin:13px 0 0;padding:15px;border-radius:13px;background:#101a31;color:#c9d8fa;font:12px/1.65 ui-monospace,SFMono-Regular,Menlo,monospace;white-space:pre-wrap;word-break:break-word}} .result{{margin-top:12px;font-size:13px;font-weight:700;word-break:break-all}} .secondary{{margin:12px 0 0;border:1px solid #dce3ef;border-radius:10px;padding:9px 12px;background:#fff;color:#30405d;font:650 13px inherit;cursor:pointer}} details summary{{cursor:pointer;font-weight:800}} details p{{color:var(--muted);font-size:12px;line-height:1.65}} .login-actions{{display:flex;gap:9px;align-items:end}} .login-actions button{{white-space:nowrap}} .privacy{{margin-top:14px;color:var(--muted);font-size:12px;line-height:1.6}}
@media(max-width:780px){{main{{padding:24px 14px 40px}} .hero,.layout{{display:block}} .local{{display:inline-block;margin-top:16px}} .side{{margin-top:18px}} .field-grid{{grid-template-columns:1fr}} .preset-row{{grid-template-columns:1fr}} .card{{padding:18px}}}}
</style></head><body><main><header class='hero'><div><div class='eyebrow'><i></i> Subtitle workspace</div><h1>抖音字幕工作台</h1><p class='sub'>批量采集、并发提取音频、可调 Whisper 转写速度，并将结果整理为按作者归档的 Excel。</p></div><div class='local'>仅在本机 127.0.0.1 运行</div></header>
<div class='layout'><div><form id='form' class='card'><div class='section-title'><span>创建提取任务</span><span class='hint'>一行一个作者主页链接</span></div><label>作者主页链接</label><textarea name='urls' placeholder='https://www.douyin.com/user/...'></textarea><label>速度预设</label><div class='preset-row'><button class='preset' type='button' data-preset='speed'><strong>速度优先</strong><span>base · 快速搜索 · 2 路转写</span></button><button class='preset active' type='button' data-preset='balanced'><strong>均衡推荐</strong><span>small · 清晰度与速度平衡</span></button><button class='preset' type='button' data-preset='quality'><strong>准确优先</strong><span>medium · 更细致，耗时更长</span></button></div><div class='field-grid'><div><label>输出目录</label><input name='output' value='{default_output}'></div><div><label>转写模型</label><select name='model'><option value='base'>base（更快）</option><option value='small' selected>small（均衡）</option><option value='medium'>medium（更准确）</option></select></div><div><label>语言</label><select name='language'><option value='zh' selected>中文</option><option value='auto'>自动识别</option><option value='en'>英语</option></select></div><div><label>音频并发</label><select name='audio_workers'><option value='2'>2 路（更稳）</option><option value='3' selected>3 路（推荐）</option><option value='4'>4 路（较快）</option></select></div><div><label>转写并发</label><select name='transcription_workers'><option value='1' selected>1 路（推荐）</option><option value='2'>2 路（速度优先）</option></select></div><div><label>搜索宽度</label><select name='beam_size'><option value='1'>1（最快）</option><option value='3' selected>3（均衡）</option><option value='5'>5（更细致）</option></select></div></div><div class='checks'><label class='check'><input type='checkbox' name='cleanup_source_videos' checked>完成后清理已成功处理的原视频</label></div><div class='notice'>任务固定使用本机 CPU 转写；音频只作临时中间文件，完成或失败后都会自动删除。请仅处理你有权下载、转写和使用的公开内容，并遵守平台规则与访问频率限制。</div><button id='run' class='primary'><span>开始批量提取</span><span>→</span></button></form>
<section class='card'><details><summary>抖音登录与 Cookie（可选）</summary><p>扫码会话和手动 Cookie 只保存在本机，不会出现在 Excel、日志或网页响应中。</p><button type='button' id='qrLogin' class='secondary'>打开扫码登录窗口</button><label>手动保存 Cookie（备用）</label><div class='login-actions'><input id='cookieHeader' type='password' autocomplete='off' placeholder='仅本机保存，不显示内容'><button type='button' id='saveCookie' class='secondary'>保存</button></div></details></section></div>
<aside class='side'><section class='card'><div class='status-top'><div class='section-title'><span>任务状态</span></div><span id='statusDot' class='status-dot'>等待任务</span></div><div class='progress'><i id='progressBar'></i></div><div id='progressCopy' class='progress-copy'>选择预设并粘贴主页链接后即可开始。</div><div class='stat-grid'><div class='stat'><b id='audioWorkers'>3</b><span>音频并发路数</span></div><div class='stat'><b id='transcribeWorkers'>1</b><span>转写并发路数</span></div></div></section><section class='card'><div class='section-title'><span>实时日志</span><span class='hint'>最近 400 条</span></div><pre id='logs'>等待开始…</pre><div class='result' id='result'></div></section></aside></div></main>
<script>const form=document.querySelector('#form'),run=document.querySelector('#run'),logs=document.querySelector('#logs'),result=document.querySelector('#result'),saveCookie=document.querySelector('#saveCookie'),cookieHeader=document.querySelector('#cookieHeader'),qrLogin=document.querySelector('#qrLogin'),statusDot=document.querySelector('#statusDot'),progressBar=document.querySelector('#progressBar'),progressCopy=document.querySelector('#progressCopy'),audioWorkers=document.querySelector('#audioWorkers'),transcribeWorkers=document.querySelector('#transcribeWorkers');
const presets={{speed:{{model:'base',audio_workers:'4',transcription_workers:'2',beam_size:'1'}},balanced:{{model:'small',audio_workers:'3',transcription_workers:'1',beam_size:'3'}},quality:{{model:'medium',audio_workers:'2',transcription_workers:'1',beam_size:'5'}}}};
function updateWorkerStats(){{audioWorkers.textContent=form.audio_workers.value;transcribeWorkers.textContent=form.transcription_workers.value}} document.querySelectorAll('.preset').forEach(button=>button.addEventListener('click',()=>{{const preset=presets[button.dataset.preset];Object.entries(preset).forEach(([key,value])=>form.elements[key].value=value);document.querySelectorAll('.preset').forEach(item=>item.classList.toggle('active',item===button));updateWorkerStats()}})); form.audio_workers.addEventListener('change',updateWorkerStats);form.transcription_workers.addEventListener('change',updateWorkerStats);
form.addEventListener('submit',async e=>{{e.preventDefault();const d=new FormData(form);const p=Object.fromEntries(d.entries());p.cleanup_source_videos=d.has('cleanup_source_videos');const r=await fetch('/api/start',{{method:'POST',headers:{{'Content-Type':'application/json'}},body:JSON.stringify(p)}});const j=await r.json();if(j.error)alert(j.error);}});
saveCookie.addEventListener('click',async()=>{{const r=await fetch('/api/session',{{method:'POST',headers:{{'Content-Type':'application/json'}},body:JSON.stringify({{cookie:cookieHeader.value}})}});const j=await r.json();if(j.error){{alert(j.error);return;}}cookieHeader.value='';alert('已仅保存到本机。');}});qrLogin.addEventListener('click',async()=>{{const r=await fetch('/api/login',{{method:'POST'}});const j=await r.json();if(j.error)alert(j.error);}});
function showProgress(lines,running){{const line=[...lines].reverse().find(item=>/\\[(\\d+)\\/(\\d+)\\] (提取音频|转写)/.test(item));if(line){{const m=line.match(/\\[(\\d+)\\/(\\d+)\\] (提取音频|转写)/);const percent=Math.round(Number(m[1])/Number(m[2])*100);progressBar.style.width=percent+'%';progressCopy.textContent=m[3]+'：'+m[1]+' / '+m[2]+'（'+percent+'%）'}}else if(running){{progressBar.style.width='8%';progressCopy.textContent='正在准备采集与任务队列…'}}else{{progressBar.style.width='0%';progressCopy.textContent='选择预设并粘贴主页链接后即可开始。'}}}}
    async function refresh(){{const s=await (await fetch('/api/status')).json();logs.textContent=s.logs.join('\\n')||'等待开始…';result.textContent=s.error?('错误：'+s.error):(s.result?'完成：'+s.result:'');run.disabled=s.running||s.login_running;run.innerHTML=s.running?'<span>正在执行任务</span><span>···</span>':'<span>开始批量提取</span><span>→</span>';qrLogin.disabled=s.running||s.login_running;qrLogin.textContent=s.login_running?'等待扫码登录…':'打开扫码登录窗口';statusDot.classList.toggle('live',s.running);statusDot.textContent=s.running?'任务运行中':(s.error?'任务需处理':'等待任务');showProgress(s.logs,s.running)}}setInterval(refresh,900);updateWorkerStats();refresh();</script></body></html>"""


def page() -> str:
    # Keep the interface self-contained: the optional preview template is not
    # required when the project is cloned or installed on another machine.
    return legacy_page()


def start_job(payload):
    urls = parse_urls(str(payload.get("urls", "")))
    if not urls:
        raise ValueError("请至少输入一个作者主页链接。")
    output_dir = Path(str(payload.get("output") or DEFAULT_OUTPUT)).expanduser()
    strategy = STRATEGIES.get(str(payload.get("strategy") or ""), {})
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
                model=str(strategy.get("model") or payload.get("model") or "small"),
                language=None if payload.get("language") == "auto" else str(payload.get("language") or "zh"),
                audio_workers=int(strategy.get("audio_workers") or payload.get("audio_workers") or 3),
                transcription_workers=int(
                    strategy.get("transcription_workers") or payload.get("transcription_workers") or 1
                ),
                beam_size=int(strategy.get("beam_size") or payload.get("beam_size") or 3),
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
