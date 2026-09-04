# -*- coding: utf-8 -*-
"""
微信 Adapter —— iLink / WeChat 客服消息方向（仅私聊），零第三方依赖：
- 接收：内置 HTTP 服务承载 iLink/微信事件推送（POST JSON）
- 发送：HTTP POST 到配置的 iLink REST 端点（客服消息风格）
- 只做私聊；不实现微信群。
配置(置于 config.json 的 "wechat" 内):
{
  "ilk": "https://你的-iLink端点/api/cgi-bin/message",  # 发送端点前缀
  "access_token": "xxx",                                # iLink/客服 凭据
  "webhook_local": "127.0.0.1:18087",                   # 本机接收端口
  "webhook_path": "/ilink"                              # 接收路径
}
真实上线：需要你在微信开放平台/iLink 侧创建应用并把事件推送到本 webhook。未配置 ilk 时仍可接收，发送会报错（提示需配置）。
"""
import json, urllib.request, urllib.error, threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from .base import BaseAdapter

class _H(BaseHTTPRequestHandler):
    adapter = None
    def log_message(self,*a): pass
    def do_POST(self):
        ln = int(self.headers.get("Content-Length") or 0)
        body = self.rfile.read(ln).decode("utf-8","ignore")
        self.send_response(200); self.end_headers(); self.wfile.write(b'{"ok":true}')
        try: ev = json.loads(body)
        except Exception: return
        threading.Thread(target=self.adapter._on_event, args=(ev,), daemon=True).start()

class WechatAdapter(BaseAdapter):
    name = "wechat"
    def __init__(self, cfg):
        super().__init__(cfg)
        c = cfg.get("wechat") or {}
        self.ilk           = (c.get("ilk") or "").rstrip("/")
        self.access_token  = c.get("access_token") or ""
        wh = (c.get("webhook_local") or "127.0.0.1:18087").split(":")
        self.wh_host, self.wh_port = wh[0], int(wh[1])
        self.wh_path = c.get("webhook_path") or "/ilink"
        self._http = None; self._t = None

    def start(self):
        _H.adapter = self
        self._http = ThreadingHTTPServer((self.wh_host, self.wh_port), _H)
        self._t = threading.Thread(target=self._http.serve_forever, daemon=True)
        self._t.start()
        print(f"[WechatAdapter] 接收 {self.wh_host}:{self.wh_port}{self.wh_path} | ilk={self.ilk or '(未配置)'}", flush=True)

    def _on_event(self, ev):
        try:
            if ev.get("type") != "message":
                return
            openid = str(ev.get("openid") or ev.get("from") or "")
            text = (ev.get("text") or "").strip()
            att = ev.get("attachments") or []
            if not openid or not (text or att):
                return
            self.receive({
                "platform": "wechat",
                "conversation_id": f"private:{openid}",
                "sender_id": openid,
                "message_id": str(ev.get("message_id") or ""),
                "text": text,
                "attachments": [a for a in att if a],
            })
        except Exception as e:
            print(f"[WechatAdapter] 处理事件出错: {e}", file=__import__("sys").stderr)

    # ---- 发送：微信客服消息风格 ----
    def _post(self, action, payload):
        if not self.ilk:
            raise RuntimeError("未配置 wechat.ilk（iLink 发送端点）。微信真实接入需先在微信/iLink 侧建应用并配置本适配器。")
        url = f"{self.ilk}/{action}" + (f"?access_token={self.access_token}" if self.access_token else "")
        req = urllib.request.Request(url, data=json.dumps(payload).encode("utf-8"),
              headers={"Content-Type":"application/json"}, method="POST")
        try:
            with urllib.request.urlopen(req, timeout=20) as r:
                r.read()
        except urllib.error.HTTPError as e:
            raise RuntimeError(f"iLink {action} 失败 {e.code}: {e.read().decode('utf-8','ignore')[:200]}")
        except Exception as e:
            raise RuntimeError(f"iLink {action} 网络错误: {e}")

    def _touser(self, msg):
        cid = msg.get("conversation_id")
        return cid[8:] if cid.startswith("private:") else cid

    def send_text(self, msg, text):
        self._post("send", {"touser": self._touser(msg),
                            "type": "text", "text": {"content": text}})

    def send_file(self, msg, path):
        import os
        if not os.path.exists(path):
            raise RuntimeError(f"文件不存在: {path}")
        name = os.path.basename(path)
        self._post("send", {"touser": self._touser(msg),
                            "type": "file", "file": {"path": path, "name": name}})
