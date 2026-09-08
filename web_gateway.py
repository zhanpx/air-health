#!/usr/bin/env python3
"""Authenticated loopback gateway for the Air Health dashboard.

The health application keeps listening on 127.0.0.1:8765.  This gateway
listens on a second loopback port and is the only origin exposed by the HTTPS
tunnel.  OAuth/setup endpoints are deliberately unavailable through it.
"""

import base64
import hashlib
import hmac
import html
import http.client
import os
import threading
import time
import urllib.parse
from http import cookies
from http.server import BaseHTTPRequestHandler, HTTPServer
from socketserver import ThreadingMixIn


LISTEN_HOST = os.environ.get("AIR_HEALTH_GATEWAY_HOST", "127.0.0.1")
LISTEN_PORT = int(os.environ.get("AIR_HEALTH_GATEWAY_PORT", "8766"))
UPSTREAM_HOST = os.environ.get("AIR_HEALTH_UPSTREAM_HOST", "127.0.0.1")
UPSTREAM_PORT = int(os.environ.get("AIR_HEALTH_UPSTREAM_PORT", "8765"))
WEB_USER = os.environ.get("AIR_HEALTH_WEB_USER", "airhealth")
PASSWORD_SHA256 = os.environ.get("AIR_HEALTH_WEB_PASSWORD_SHA256", "")
SESSION_SECRET = os.environ.get("AIR_HEALTH_WEB_SESSION_SECRET", "").encode("utf-8")
SESSION_TTL = int(os.environ.get("AIR_HEALTH_WEB_SESSION_TTL", "43200"))
LOGIN_WINDOW = 900
LOGIN_MAX_FAILURES = 8
LOGIN_FAILURES = {}
LOGIN_LOCK = threading.Lock()

ALLOWED_GET = {
    "/",
    "/index.html",
    "/static/app.css",
    "/static/mobile.css",
    "/static/app.js",
    "/api/status",
    "/api/dashboard",
    "/api/daily-brief",
    "/api/backup-status",
    "/api/long-term-trends",
    "/api/report-archive",
    "/api/training-plan",
    "/api/weekly-report",
}
ALLOWED_POST = {
    "/api/sync", "/api/ai/analyze", "/api/ai/training", "/api/ai/workout", "/api/assistant/chat",
    "/api/backup/create", "/api/daily-brief/generate", "/api/weekly-report/generate",
}
HOP_BY_HOP = {
    "connection",
    "keep-alive",
    "proxy-authenticate",
    "proxy-authorization",
    "te",
    "trailers",
    "transfer-encoding",
    "upgrade",
}


class ThreadingHTTPServer(ThreadingMixIn, HTTPServer):
    daemon_threads = True


def _b64url(data):
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _signature(expiry):
    return _b64url(hmac.new(SESSION_SECRET, expiry.encode("ascii"), hashlib.sha256).digest())


def _new_session():
    expiry = str(int(time.time()) + SESSION_TTL)
    return expiry + "." + _signature(expiry)


def _valid_session(value):
    if not value or "." not in value or not SESSION_SECRET:
        return False
    expiry, signature = value.split(".", 1)
    try:
        if int(expiry) < int(time.time()):
            return False
    except ValueError:
        return False
    return hmac.compare_digest(signature, _signature(expiry))


def _login_page(error=""):
    error_html = ""
    if error:
        error_html = '<p class="error">{}</p>'.format(html.escape(error))
    return ("""<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>登录 · Air Health</title>
<style>
*{box-sizing:border-box}body{margin:0;min-height:100vh;display:grid;place-items:center;
font-family:-apple-system,BlinkMacSystemFont,"Segoe UI","PingFang SC",sans-serif;
color:#183129;background:radial-gradient(circle at 80% 12%,#e8f6ef,transparent 36%),#f4f7f3}
.card{width:min(92vw,420px);background:rgba(255,255,255,.94);border:1px solid #e1e9e3;
border-radius:28px;padding:38px;box-shadow:0 24px 70px rgba(25,59,46,.12)}
.logo{width:54px;height:54px;border-radius:16px;display:grid;place-items:center;background:#26775a;
color:white;font-size:25px;font-weight:700}.eyebrow{margin:25px 0 8px;color:#26775a;font-size:12px;
font-weight:800;letter-spacing:.18em}.title{font-family:Georgia,"Songti SC",serif;font-size:34px;margin:0 0 8px}
.sub{color:#708078;margin:0 0 28px}.field{display:block;font-size:13px;font-weight:700;margin:16px 0 7px}
input{width:100%;border:1px solid #cedbd3;border-radius:13px;padding:13px 14px;font-size:16px;outline:none}
input:focus{border-color:#26775a;box-shadow:0 0 0 3px #26775a18}button{width:100%;border:0;
border-radius:13px;padding:14px;margin-top:22px;background:#1f684e;color:#fff;font-size:16px;font-weight:750;
cursor:pointer}.error{color:#a33b30;background:#fff2ef;border-radius:10px;padding:10px 12px;font-size:13px}
.privacy{font-size:12px;line-height:1.6;color:#87948d;margin:18px 0 0;text-align:center}
</style></head><body><main class="card"><div class="logo">▥</div>
<p class="eyebrow">PRIVATE HEALTH DASHBOARD</p><h1 class="title">Air Health</h1>
<p class="sub">登录后查看你的健康趋势与同步状态。</p>{error}
<form method="post" action="/login" autocomplete="on">
<label class="field" for="username">用户名</label><input id="username" name="username" autocomplete="username" required>
<label class="field" for="password">密码</label><input id="password" name="password" type="password" autocomplete="current-password" required>
<button type="submit">安全登录</button></form>
<p class="privacy">连接使用 HTTPS；Google OAuth 配置与令牌不通过此公网入口开放。</p>
</main></body></html>""").replace("{error}", error_html).encode("utf-8")


class GatewayHandler(BaseHTTPRequestHandler):
    server_version = "AirHealthGateway/1.0"
    sys_version = ""
    protocol_version = "HTTP/1.1"

    def version_string(self):
        return "AirHealthGateway"

    def log_message(self, fmt, *args):
        # Avoid placing paths and health-query details in the system journal.
        print('{} - {}'.format(self.client_address[0], fmt % args))

    def _security_headers(self):
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Security-Policy", "default-src 'self'; style-src 'self' 'unsafe-inline'; script-src 'self'; img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header("Strict-Transport-Security", "max-age=31536000")
        self.send_header("Permissions-Policy", "camera=(), microphone=(), geolocation=(), payment=()")

    def _send_bytes(self, status, body, content_type="text/plain; charset=utf-8", extra_headers=None):
        self.send_response(status)
        self._security_headers()
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        if extra_headers:
            for name, value in extra_headers:
                self.send_header(name, value)
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    def _cookie_session(self):
        raw = self.headers.get("Cookie", "")
        jar = cookies.SimpleCookie()
        try:
            jar.load(raw)
        except cookies.CookieError:
            return ""
        item = jar.get("air_health_session")
        return item.value if item else ""

    def _authenticated(self):
        return _valid_session(self._cookie_session())

    def _client_key(self):
        return self.headers.get("CF-Connecting-IP", self.client_address[0])[:64]

    def _login_blocked(self):
        now = time.time()
        key = self._client_key()
        with LOGIN_LOCK:
            recent = [stamp for stamp in LOGIN_FAILURES.get(key, []) if stamp > now - LOGIN_WINDOW]
            LOGIN_FAILURES[key] = recent
            return len(recent) >= LOGIN_MAX_FAILURES

    def _record_login_failure(self):
        key = self._client_key()
        with LOGIN_LOCK:
            LOGIN_FAILURES.setdefault(key, []).append(time.time())

    def _clear_login_failures(self):
        with LOGIN_LOCK:
            LOGIN_FAILURES.pop(self._client_key(), None)

    def _show_login(self, error="", status=200):
        self._send_bytes(status, _login_page(error), "text/html; charset=utf-8")

    def _not_found(self):
        self._send_bytes(404, b"Not found")

    def _proxy(self, body=b""):
        forwarded = {}
        for name in ("Accept", "Content-Type"):
            value = self.headers.get(name)
            if value:
                forwarded[name] = value
        forwarded["Host"] = "{}:{}".format(UPSTREAM_HOST, UPSTREAM_PORT)
        forwarded["X-Forwarded-Proto"] = "https"
        try:
            request_path = urllib.parse.urlsplit(self.path).path
            timeout = 240 if request_path in {
                "/api/ai/analyze", "/api/ai/training", "/api/ai/workout", "/api/assistant/chat",
                "/api/backup/create", "/api/daily-brief/generate", "/api/weekly-report/generate"
            } else 90
            conn = http.client.HTTPConnection(UPSTREAM_HOST, UPSTREAM_PORT, timeout=timeout)
            conn.request(self.command, self.path, body=body, headers=forwarded)
            response = conn.getresponse()
            data = response.read()
            self.send_response(response.status)
            self._security_headers()
            for name, value in response.getheaders():
                lowered = name.lower()
                if lowered not in HOP_BY_HOP and lowered not in {"content-length", "server", "date", "cache-control"}:
                    self.send_header(name, value)
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            if self.command != "HEAD":
                self.wfile.write(data)
            conn.close()
        except Exception as exc:
            print("Gateway upstream error: {}".format(exc), flush=True)
            self._send_bytes(502, b"Dashboard upstream unavailable")

    def do_HEAD(self):
        self.do_GET()

    def do_GET(self):
        path = urllib.parse.urlsplit(self.path).path
        if path == "/login":
            if self._authenticated():
                self.send_response(303)
                self._security_headers()
                self.send_header("Location", "/")
                self.send_header("Content-Length", "0")
                self.end_headers()
            else:
                self._show_login()
            return
        if not self._authenticated():
            if path.startswith("/api/"):
                self._send_bytes(401, b'{"error":"authentication required"}', "application/json; charset=utf-8")
            else:
                self._show_login()
            return
        if path not in ALLOWED_GET:
            self._not_found()
            return
        self._proxy()

    def do_POST(self):
        path = urllib.parse.urlsplit(self.path).path
        length = int(self.headers.get("Content-Length", "0") or "0")
        max_length = 5 * 1024 * 1024 if path == "/api/assistant/chat" else 65536
        if length > max_length:
            self._send_bytes(413, b"Request too large")
            return
        body = self.rfile.read(length) if length else b""
        if path == "/login":
            if self._login_blocked():
                self._send_bytes(429, b"Too many login attempts. Try again later.")
                return
            form = urllib.parse.parse_qs(body.decode("utf-8", "replace"), keep_blank_values=True)
            username = (form.get("username") or [""])[0]
            password = (form.get("password") or [""])[0]
            supplied_hash = hashlib.sha256(password.encode("utf-8")).hexdigest()
            valid = hmac.compare_digest(username, WEB_USER) and PASSWORD_SHA256 and hmac.compare_digest(supplied_hash, PASSWORD_SHA256)
            if not valid:
                self._record_login_failure()
                time.sleep(0.35)
                self._show_login("用户名或密码不正确。", 401)
                return
            self._clear_login_failures()
            cookie = "air_health_session={}; Path=/; Max-Age={}; Secure; HttpOnly; SameSite=Strict".format(_new_session(), SESSION_TTL)
            self.send_response(303)
            self._security_headers()
            self.send_header("Set-Cookie", cookie)
            self.send_header("Location", "/")
            self.send_header("Content-Length", "0")
            self.end_headers()
            return
        if not self._authenticated():
            self._send_bytes(401, b'{"error":"authentication required"}', "application/json; charset=utf-8")
            return
        if path not in ALLOWED_POST:
            self._not_found()
            return
        self._proxy(body)


def main():
    if not PASSWORD_SHA256 or not SESSION_SECRET:
        raise SystemExit("gateway credentials are not configured")
    server = ThreadingHTTPServer((LISTEN_HOST, LISTEN_PORT), GatewayHandler)
    print("Air Health gateway listening on {}:{}".format(LISTEN_HOST, LISTEN_PORT))
    server.serve_forever()


if __name__ == "__main__":
    main()
