"""本机交互式抖音登录：只持久化浏览器会话，不显示或导出 Cookie。"""
import json
import time
from pathlib import Path
from typing import Callable


PROJECT_DIR = Path(__file__).resolve().parents[1]
SESSION_STATE = PROJECT_DIR / ".private" / "douyin_storage_state.json"
Log = Callable[[str], None]


def session_cookie_header() -> str:
    """供本机下载器进程内部使用；绝不写入页面或日志。"""
    if not SESSION_STATE.exists():
        return ""
    try:
        state = json.loads(SESSION_STATE.read_text(encoding="utf-8"))
        return "; ".join(
            f"{item['name']}={item['value']}"
            for item in state.get("cookies", [])
            if item.get("domain", "").endswith("douyin.com") and item.get("name") and item.get("value")
        )
    except (OSError, ValueError, KeyError, TypeError):
        return ""


def login_with_qr(log: Log, timeout_seconds: int = 240) -> None:
    try:
        from playwright.sync_api import sync_playwright
    except ImportError as exc:
        raise RuntimeError("扫码组件未安装。请先双击“安装全部组件.command”。") from exc

    SESSION_STATE.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    log("正在打开本机登录浏览器，请在窗口中使用抖音 App 扫码登录。")
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=False)
        context = browser.new_context(locale="zh-CN")
        page = context.new_page()
        try:
            page.goto("https://www.douyin.com/", wait_until="domcontentloaded", timeout=60000)
            deadline = time.monotonic() + timeout_seconds
            while time.monotonic() < deadline:
                names = {item.get("name") for item in context.cookies("https://www.douyin.com/")}
                if "sessionid_ss" in names or "sessionid" in names:
                    context.storage_state(path=str(SESSION_STATE))
                    SESSION_STATE.chmod(0o600)
                    log("扫码登录成功，会话已仅保存在本机。可以关闭登录浏览器窗口。")
                    return
                time.sleep(2)
        finally:
            browser.close()
    raise RuntimeError("扫码登录超时或未检测到登录会话，请重新尝试。")
