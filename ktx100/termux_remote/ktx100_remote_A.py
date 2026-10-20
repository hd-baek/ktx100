#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from __future__ import annotations
import json, secrets, threading, time, shutil, hmac
from pathlib import Path
import pexpect, pyte
from flask import Flask, jsonify, make_response, request

NAME = "A"
PORT = 8765
APP_DIR = Path.home() / ".ktx100-remote-a"
CONFIG_FILE = APP_DIR / "config.json"
LOG_FILE = APP_DIR / "remote.log"
ROWS, COLS = 36, 112
app = Flask(__name__)

def log(msg):
    APP_DIR.mkdir(parents=True, exist_ok=True)
    line = f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {msg}\n"
    try:
        with LOG_FILE.open("a", encoding="utf-8") as f: f.write(line)
    except Exception: pass
    try: print(line, end="", flush=True)
    except Exception: pass

def load_config():
    APP_DIR.mkdir(parents=True, exist_ok=True)
    data = {}
    if CONFIG_FILE.exists():
        try: data = json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
        except Exception: data = {}
    if not data.get("access_key"):
        data["access_key"] = secrets.token_urlsafe(24)
        data["port"] = PORT
        CONFIG_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return data

CONFIG = load_config()
ACCESS_KEY = str(CONFIG["access_key"])

class Terminal:
    def __init__(self):
        self.lock = threading.RLock()
        self.proc = None
        self.screen = pyte.Screen(COLS, ROWS)
        self.stream = pyte.Stream(self.screen)
        self.revision = 0
        self.started_at = None
        self.last_error = None

    def _new_screen(self):
        self.screen = pyte.Screen(COLS, ROWS)
        self.stream = pyte.Stream(self.screen)
        self.revision += 1

    def is_running(self):
        return self.proc is not None and self.proc.isalive()

    def start(self):
        with self.lock:
            if self.is_running(): return False, "이미 KTX100이 실행 중입니다."
            exe = shutil.which("ktx100")
            if not exe: return False, "ktx100 명령을 찾지 못했습니다."
            self._new_screen()
            try:
                self.proc = pexpect.spawn(exe, encoding="utf-8", codec_errors="replace", echo=False)
                try: self.proc.setwinsize(ROWS, COLS)
                except Exception: pass
            except Exception as e:
                self.proc = None
                self.last_error = f"{type(e).__name__}: {e}"
                return False, self.last_error
            self.started_at = time.time()
            threading.Thread(target=self._reader_loop, daemon=True).start()
            log(f"KTX100 started: {exe}")
            return True, "KTX100을 시작했습니다."

    def _reader_loop(self):
        while True:
            with self.lock: proc = self.proc
            if proc is None: return
            try:
                data = proc.read_nonblocking(size=4096, timeout=0.15)
                if data:
                    with self.lock:
                        self.stream.feed(data)
                        self.revision += 1
            except pexpect.TIMEOUT:
                continue
            except pexpect.EOF:
                with self.lock: self.revision += 1
                return
            except Exception as e:
                with self.lock:
                    self.last_error = f"{type(e).__name__}: {e}"
                    self.revision += 1
                return

    def write(self, text):
        with self.lock:
            if not self.is_running(): return False
            try:
                self.proc.send(text)
                return True
            except Exception as e:
                self.last_error = f"{type(e).__name__}: {e}"
                return False

    def key(self, name):
        seq = {"up":"\x1b[A","down":"\x1b[B","left":"\x1b[D","right":"\x1b[C","enter":"\r","space":" ","esc":"\x1b","tab":"\t","back":"\x7f"}.get(name)
        return False if seq is None else self.write(seq)

    def send_text(self, text, press_enter=False):
        return self.write(text + ("\r" if press_enter else ""))

    def ctrl_c(self):
        with self.lock:
            if not self.is_running(): return False
            try:
                self.proc.sendcontrol("c"); return True
            except Exception:
                return self.write("\x03")

    def stop(self):
        with self.lock:
            if not self.is_running(): return False
            try:
                self.proc.sendcontrol("c")
                time.sleep(0.3)
                if self.proc.isalive(): self.proc.terminate(force=True)
            except Exception: pass
            self.revision += 1
            return True

    def state(self, include_screen=True):
        with self.lock:
            running = self.is_running()
            elapsed = int(time.time() - self.started_at) if running and self.started_at else 0
            out = {"running":running,"elapsed":elapsed,"revision":self.revision,"error":self.last_error}
            if include_screen:
                lines = [x.rstrip() for x in self.screen.display]
                while lines and not lines[0]: lines.pop(0)
                while lines and not lines[-1]: lines.pop()
                out["screen"] = "\n".join(lines) if lines else "(화면 출력 없음)"
            return out

terminal = Terminal()

def auth_ok():
    supplied = request.headers.get("X-Access-Key","")
    return bool(supplied) and hmac.compare_digest(supplied, ACCESS_KEY)

@app.after_request
def no_cache(resp):
    resp.headers["Cache-Control"]="no-store, no-cache, must-revalidate, max-age=0"
    resp.headers["Pragma"]="no-cache"
    return resp

@app.get("/")
def index(): return make_response(INDEX_HTML)

@app.get("/api/state")
def api_state():
    if not auth_ok(): return jsonify({"ok":False,"error":"unauthorized"}),401
    try: since=int(request.args.get("since","-1"))
    except ValueError: since=-1
    rev=terminal.state(False)["revision"]
    st=terminal.state(since!=rev); st["ok"]=True
    return jsonify(st)

@app.post("/api/start")
def api_start():
    if not auth_ok(): return jsonify({"ok":False}),401
    ok,msg=terminal.start(); return jsonify({"ok":ok,"message":msg})

@app.post("/api/stop")
def api_stop():
    if not auth_ok(): return jsonify({"ok":False}),401
    return jsonify({"ok":terminal.stop()})

@app.post("/api/action")
def api_action():
    if not auth_ok(): return jsonify({"ok":False}),401
    b=request.get_json(silent=True) or {}
    a=str(b.get("action",""))
    ok=terminal.ctrl_c() if a=="ctrlc" else terminal.key(a)
    return jsonify({"ok":bool(ok)})

@app.post("/api/text")
def api_text():
    if not auth_ok(): return jsonify({"ok":False}),401
    b=request.get_json(silent=True) or {}
    t=str(b.get("text",""))
    if len(t)>300: return jsonify({"ok":False}),400
    return jsonify({"ok":terminal.send_text(t,bool(b.get("enter",False)))})

INDEX_HTML = r"""<!doctype html><html lang="ko"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover,user-scalable=no">
<title>KTX100 A</title>
<style>
:root{color-scheme:dark;font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif}
*{box-sizing:border-box;-webkit-tap-highlight-color:transparent}body{margin:0;background:#0b0b0c;color:#f5f5f7;padding:12px}.wrap{max-width:720px;margin:auto}
.top{display:flex;justify-content:space-between;align-items:center;gap:8px;margin-bottom:10px}.status{padding:6px 9px;border-radius:999px;background:#3b2020}.status.on{background:#153c23}
.card{background:#171719;border:1px solid #2d2d30;border-radius:15px;padding:10px;margin-bottom:10px}.screen{white-space:pre;overflow:auto;height:min(48vh,430px);min-height:260px;background:#050506;border-radius:11px;padding:10px;font:12px/1.38 ui-monospace,monospace}
.row{display:flex;gap:8px;margin-top:8px}.pad{display:grid;grid-template-columns:repeat(3,1fr);gap:8px}button{border:0;border-radius:13px;background:#2b2b2e;color:white;min-height:52px;font-size:17px;font-weight:650;flex:1}.pad button{min-height:58px;font-size:22px}
.primary{background:#1e6b36}.danger{background:#7b2525}.blank{visibility:hidden}.inputrow{display:flex;gap:8px;margin-top:8px}input{min-width:0;flex:1;background:#0d0d0f;color:white;border:1px solid #38383c;border-radius:12px;padding:0 12px;font-size:16px}
#login{position:fixed;inset:0;background:rgba(0,0,0,.92);display:none;place-items:center;padding:20px;z-index:100}#login .box{width:min(420px,100%);background:#19191b;border:1px solid #333;border-radius:18px;padding:18px}#login input{width:100%;height:50px;margin:12px 0}
</style></head><body>
<div id="login"><div class="box"><h2>KTX100 A 연결</h2><input id="keyInput" type="password" placeholder="Access Key"><button class="primary" onclick="saveKey()">연결</button><div id="error"></div></div></div>
<div class="wrap"><div class="top"><h1>🚄 KTX100 A</h1><div id="status" class="status">연결 중…</div></div>
<div class="card"><div id="screen" class="screen">연결 중…</div><div class="row"><button onclick="refresh(true)">↻ 화면 갱신</button><button onclick="act('esc')">Esc</button><button onclick="act('back')">⌫ Back</button></div></div>
<div class="card"><div class="pad"><button class="blank">·</button><button onclick="act('up')">↑</button><button class="blank">·</button><button onclick="act('left')">←</button><button onclick="act('enter')">Enter</button><button onclick="act('right')">→</button><button onclick="ctrlc()">Ctrl+C</button><button onclick="act('down')">↓</button><button onclick="act('space')">Space</button></div>
<div class="row"><button class="primary" onclick="quickAnswer('y')">Y 네</button><button class="danger" onclick="quickAnswer('n')">N 아니오</button></div>
<div class="inputrow"><input id="textInput" placeholder="문자 입력"><button onclick="sendText(false)">입력</button><button onclick="sendText(true)">입력↵</button></div>
<div class="row"><button class="primary" onclick="startK()">KTX100 시작</button><button class="danger" onclick="stopK()">종료</button></div></div></div>
<script>
let accessKey=localStorage.getItem("ktx100RemoteKey_A")||"";let revision=-1;
const fragment=location.hash?decodeURIComponent(location.hash.slice(1)):"";
if(fragment&&!accessKey){accessKey=fragment;localStorage.setItem("ktx100RemoteKey_A",accessKey);history.replaceState(null,"",location.pathname)}
function showLogin(msg=""){document.getElementById("login").style.display="grid";document.getElementById("error").textContent=msg}function hideLogin(){document.getElementById("login").style.display="none"}
function saveKey(){const k=document.getElementById("keyInput").value.trim();if(!k)return;accessKey=k;localStorage.setItem("ktx100RemoteKey_A",k);hideLogin();revision=-1;refresh(true)}
async function api(path,options={}){if(!accessKey){showLogin();throw new Error("no key")}const headers=Object.assign({},options.headers||{},{"X-Access-Key":accessKey});const r=await fetch(path,Object.assign({},options,{headers,cache:"no-store"}));if(r.status===401){localStorage.removeItem("ktx100RemoteKey_A");accessKey="";showLogin("Access Key가 맞지 않습니다.");throw new Error("unauthorized")}return await r.json()}
function setStatus(d){const e=document.getElementById("status");if(d.running){e.className="status on";e.textContent="🟢 실행 중"}else{e.className="status";e.textContent="🔴 정지"}}
async function refresh(force=false){try{const d=await api(`/api/state?since=${force?-1:revision}`);setStatus(d);revision=d.revision;if(typeof d.screen==="string"){const s=document.getElementById("screen");s.textContent=d.screen;requestAnimationFrame(()=>{s.scrollTop=s.scrollHeight})}}catch(e){if(String(e).includes("unauthorized")||String(e).includes("no key"))return;document.getElementById("status").textContent="🔴 연결 끊김"}}
async function act(a){await api("/api/action",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({action:a})});setTimeout(()=>refresh(true),80)}
async function ctrlc(){await act("ctrlc")}async function quickAnswer(v){await api("/api/text",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({text:v,enter:true})});setTimeout(()=>refresh(true),80)}
async function sendText(enter){const el=document.getElementById("textInput");const t=el.value;await api("/api/text",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({text:t,enter:enter})});el.value="";setTimeout(()=>refresh(true),80)}
async function startK(){await api("/api/start",{method:"POST"});setTimeout(()=>refresh(true),200)}async function stopK(){await api("/api/stop",{method:"POST"});setTimeout(()=>refresh(true),200)}
if(!accessKey)showLogin();else hideLogin();refresh(true);setInterval(()=>{if(!document.hidden)refresh(false)},350);
</script></body></html>"""

if __name__ == "__main__":
    print("="*58)
    print(f"KTX100 {NAME} Remote / Termux")
    print(f"Port: {PORT}")
    print(f"Access Key: {ACCESS_KEY}")
    print("="*58)
    log(f"KTX100 {NAME} remote starting on 0.0.0.0:{PORT}")
    app.run(host="0.0.0.0", port=PORT, debug=False, threaded=True)
