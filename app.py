# app.py
# Joey's Cloud — 2 tabs, clean glass UI, folder upload in CHUNKS + progress bar (no hanging)
# Run:  python3 app.py
# Env vars:
#   ADMIN_USER, ADMIN_PASS, FLASK_SECRET_KEY
#   MAX_UPLOAD_BYTES (default 20GB)  e.g. export MAX_UPLOAD_BYTES=$((50*1024*1024*1024))

from flask import Flask, request, redirect, session, jsonify, send_from_directory
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
import os, sqlite3, time, shutil

APP_TITLE = "Joey's Cloud"
HOST = "0.0.0.0"
PORT = 8000

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "data")
STORAGE_DIR = os.path.join(BASE_DIR, "storage")
DB_PATH = os.path.join(DATA_DIR, "cloud.db")

os.makedirs(DATA_DIR, exist_ok=True)
os.makedirs(STORAGE_DIR, exist_ok=True)

DEFAULT_ADMIN_USERNAME = os.environ.get("ADMIN_USER", "joey")
DEFAULT_ADMIN_PASSWORD = os.environ.get("ADMIN_PASS", "change-me-now")

app = Flask(__name__)
app.secret_key = os.environ.get("FLASK_SECRET_KEY", "dev-secret-change-me")

# Sessions/cookies reliable for fetch
app.config.update(
    SESSION_COOKIE_SAMESITE="Lax",
    SESSION_COOKIE_HTTPONLY=True,
)

# Upload limits (413 fix)
app.config["MAX_CONTENT_LENGTH"] = int(os.environ.get("MAX_UPLOAD_BYTES", 20 * 1024 * 1024 * 1024))  # 20GB default
app.config["MAX_FORM_MEMORY_SIZE"] = int(os.environ.get("MAX_FORM_MEMORY_SIZE", 64 * 1024 * 1024))  # 64MB in RAM

# ---------------- DB ----------------

def db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = db()
    cur = conn.cursor()

    cur.execute("""
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT UNIQUE NOT NULL,
        pass_hash TEXT NOT NULL,
        is_admin INTEGER NOT NULL DEFAULT 0,
        created_at INTEGER NOT NULL
    )
    """)
    conn.commit()

    cur.execute("SELECT id FROM users WHERE username=?", (DEFAULT_ADMIN_USERNAME,))
    row = cur.fetchone()
    if not row:
        cur.execute(
            "INSERT INTO users (username, pass_hash, is_admin, created_at) VALUES (?, ?, 1, ?)",
            (DEFAULT_ADMIN_USERNAME, generate_password_hash(DEFAULT_ADMIN_PASSWORD), int(time.time()))
        )
        conn.commit()

    conn.close()

# ---------------- Auth ----------------

def require_login():
    return bool(session.get("uid"))

def current_user():
    uid = session.get("uid")
    if not uid:
        return None
    conn = db()
    cur = conn.cursor()
    cur.execute("SELECT * FROM users WHERE id=?", (uid,))
    u = cur.fetchone()
    conn.close()
    return u

# ---------------- Storage helpers ----------------

def user_root(user_id: int) -> str:
    return os.path.join(STORAGE_DIR, f"user_{user_id}")

def ensure_user_storage(user_id: int):
    os.makedirs(user_root(user_id), exist_ok=True)

def safe_join(root: str, rel_path: str) -> str:
    rel_path = (rel_path or "").replace("\\", "/").lstrip("/")
    full = os.path.abspath(os.path.join(root, rel_path))
    root_abs = os.path.abspath(root)
    if not full.startswith(root_abs + os.sep) and full != root_abs:
        raise ValueError("Invalid path")
    return full

def sanitize_relpath(rel_path: str) -> str:
    rel_path = (rel_path or "").replace("\\", "/").lstrip("/")
    parts = [p for p in rel_path.split("/") if p and p not in (".", "..")]
    safe_parts = []
    for p in parts:
        sp = secure_filename(p)
        if sp:
            safe_parts.append(sp)
    return "/".join(safe_parts)

def folder_tree(root: str, rel: str = ""):
    base = safe_join(root, rel)
    if not os.path.exists(base):
        return {"name": "", "path": rel, "type": "folder", "children": []}

    def scan_dir(abs_path, rel_path):
        node = {"name": os.path.basename(abs_path) if rel_path else "", "path": rel_path, "type": "folder", "children": []}
        try:
            entries = sorted(os.listdir(abs_path), key=lambda s: s.lower())
        except PermissionError:
            return node

        for e in entries:
            ap = os.path.join(abs_path, e)
            rp = (rel_path + "/" + e).lstrip("/")
            if os.path.isdir(ap):
                node["children"].append(scan_dir(ap, rp))
            else:
                try:
                    size = os.path.getsize(ap)
                except OSError:
                    size = 0
                node["children"].append({"name": e, "path": rp, "type": "file", "size": size})
        return node

    return scan_dir(base, rel)

def dir_size_bytes(path: str) -> int:
    total = 0
    for r, _, files in os.walk(path):
        for f in files:
            fp = os.path.join(r, f)
            try:
                total += os.path.getsize(fp)
            except OSError:
                pass
    return total

def count_files(path: str) -> int:
    c = 0
    for _, _, files in os.walk(path):
        c += len(files)
    return c

def fmt_bytes(n: int) -> str:
    units = ["B", "KB", "MB", "GB", "TB"]
    x = float(n)
    for u in units:
        if x < 1024 or u == units[-1]:
            return f"{x:.1f} {u}" if u != "B" else f"{int(x)} B"
        x /= 1024.0

def disk_stats():
    usage = shutil.disk_usage(STORAGE_DIR)
    return {"total": usage.total, "used": usage.used, "free": usage.free}

# ---------------- Errors ----------------

@app.errorhandler(413)
def too_large(e):
    return jsonify({"ok": False, "msg": "Upload too large (413). Increase MAX_UPLOAD_BYTES or use smaller chunks."}), 413

# ---------------- Pages ----------------

LOGIN_HTML = """
<!doctype html><html><head>
<meta charset="utf-8"/><meta name="viewport" content="width=device-width,initial-scale=1"/>
<title>Login - __TITLE__</title>
<style>
  :root{--bg:#0b0f16;--card:rgba(20,27,42,.92);--border:rgba(255,255,255,.10);--text:#e8eefc;--muted:rgba(232,238,252,.75);}
  *{box-sizing:border-box}
  body{margin:0;font-family:system-ui,Segoe UI,Roboto,Arial;color:var(--text);min-height:100vh;display:grid;place-items:center;background:
    radial-gradient(1000px 600px at 20% 20%, rgba(122,167,255,.18), transparent 60%),
    radial-gradient(900px 600px at 80% 60%, rgba(255,122,214,.12), transparent 60%),
    var(--bg);}
  .card{width:min(440px,92vw);padding:18px;border-radius:18px;background:var(--card);border:1px solid var(--border);
    box-shadow:0 18px 60px rgba(0,0,0,.45);backdrop-filter: blur(12px);position:relative;overflow:hidden;}
  .card:before{content:"";position:absolute;inset:-2px;background:linear-gradient(135deg, rgba(122,167,255,.35), rgba(255,122,214,.18), transparent 55%);filter:blur(18px);opacity:.7;pointer-events:none}
  h1{position:relative;margin:0 0 10px;font-size:18px;letter-spacing:.2px}
  .muted{position:relative;color:var(--muted);font-size:12px;line-height:1.4;margin-bottom:10px}
  label{display:block;font-size:13px;opacity:.92;margin-top:10px;position:relative}
  input{width:100%;padding:11px 12px;border-radius:12px;border:1px solid rgba(255,255,255,.12);background:rgba(13,20,36,.78);color:var(--text);outline:none;position:relative}
  input:focus{border-color:rgba(122,167,255,.65);box-shadow:0 0 0 3px rgba(122,167,255,.10)}
  .row{display:flex;gap:10px;margin-top:12px}
  .btn{flex:1;padding:11px 12px;border-radius:12px;border:1px solid rgba(255,255,255,.12);background:rgba(27,39,66,.85);color:var(--text);
    cursor:pointer;text-decoration:none;display:inline-flex;justify-content:center;align-items:center;transition:transform .12s ease, filter .12s ease, background .12s ease;}
  .btn:hover{transform:translateY(-1px);filter:brightness(1.08)}
  .btn:active{transform:translateY(0px) scale(.99)}
  .msg{margin-top:10px;font-size:13px;color:#ffb3b3;min-height:18px;position:relative}
  code{background:rgba(13,20,36,.70);padding:2px 6px;border-radius:8px;border:1px solid rgba(255,255,255,.10)}
</style></head><body>
  <div class="card">
    <h1>__TITLE__</h1>
    <div class="muted">Admin default: <code>__ADMIN_USER__</code> (set <code>ADMIN_PASS</code> env var).</div>
    <form method="POST" action="/login">
      <label>Username</label>
      <input name="username" autocomplete="username" required />
      <label>Password</label>
      <input name="password" type="password" autocomplete="current-password" required />
      <div class="row">
        <button class="btn" type="submit">Sign in</button>
        <a class="btn" href="/register">Create account</a>
      </div>
      <div class="msg">__MSG__</div>
    </form>
  </div>
</body></html>
"""

REGISTER_HTML = """
<!doctype html><html><head>
<meta charset="utf-8"/><meta name="viewport" content="width=device-width,initial-scale=1"/>
<title>Create account - __TITLE__</title>
<style>
  :root{--bg:#0b0f16;--card:rgba(20,27,42,.92);--border:rgba(255,255,255,.10);--text:#e8eefc;--muted:rgba(232,238,252,.75);}
  *{box-sizing:border-box}
  body{margin:0;font-family:system-ui,Segoe UI,Roboto,Arial;color:var(--text);min-height:100vh;display:grid;place-items:center;background:
    radial-gradient(1000px 600px at 20% 20%, rgba(122,167,255,.18), transparent 60%),
    radial-gradient(900px 600px at 80% 60%, rgba(255,122,214,.12), transparent 60%),
    var(--bg);}
  .card{width:min(440px,92vw);padding:18px;border-radius:18px;background:var(--card);border:1px solid var(--border);
    box-shadow:0 18px 60px rgba(0,0,0,.45);backdrop-filter: blur(12px);position:relative;overflow:hidden;}
  .card:before{content:"";position:absolute;inset:-2px;background:linear-gradient(135deg, rgba(122,167,255,.35), rgba(255,122,214,.18), transparent 55%);filter:blur(18px);opacity:.7;pointer-events:none}
  h1{position:relative;margin:0 0 10px;font-size:18px;letter-spacing:.2px}
  .muted{position:relative;color:var(--muted);font-size:12px;line-height:1.4;margin-bottom:10px}
  label{display:block;font-size:13px;opacity:.92;margin-top:10px;position:relative}
  input{width:100%;padding:11px 12px;border-radius:12px;border:1px solid rgba(255,255,255,.12);background:rgba(13,20,36,.78);color:var(--text);outline:none;position:relative}
  input:focus{border-color:rgba(122,167,255,.65);box-shadow:0 0 0 3px rgba(122,167,255,.10)}
  .row{display:flex;gap:10px;margin-top:12px}
  .btn{flex:1;padding:11px 12px;border-radius:12px;border:1px solid rgba(255,255,255,.12);background:rgba(27,39,66,.85);color:var(--text);
    cursor:pointer;text-decoration:none;display:inline-flex;justify-content:center;align-items:center;transition:transform .12s ease, filter .12s ease, background .12s ease;}
  .btn:hover{transform:translateY(-1px);filter:brightness(1.08)}
  .btn:active{transform:translateY(0px) scale(.99)}
  .msg{margin-top:10px;font-size:13px;color:#ffb3b3;min-height:18px;position:relative}
</style></head><body>
  <div class="card">
    <h1>Create account</h1>
    <form method="POST" action="/register">
      <label>Username</label>
      <input name="username" autocomplete="username" required />
      <label>Password</label>
      <input name="password" type="password" autocomplete="new-password" required />
      <div class="row">
        <button class="btn" type="submit">Create</button>
        <a class="btn" href="/login">Back</a>
      </div>
      <div class="msg">__MSG__</div>
      <div class="muted">Rules: username 3–24 chars, password 6+ chars.</div>
    </form>
  </div>
</body></html>
"""

APP_HTML = """
<!doctype html><html><head>
<meta charset="utf-8"/><meta name="viewport" content="width=device-width,initial-scale=1"/>
<title>__TITLE__</title>
<style>
  :root{
    --bg:#0b0f16;
    --glass: rgba(20,27,42,.84);
    --glass2: rgba(13,20,36,.70);
    --border: rgba(255,255,255,.10);
    --text:#e8eefc;
    --muted: rgba(232,238,252,.72);
    --accent:#7aa7ff;
    --danger:#ff7a7a;
    --ok:#a8ffbf;
  }
  *{box-sizing:border-box}
  body{
    margin:0;font-family:system-ui,Segoe UI,Roboto,Arial;color:var(--text);min-height:100vh;
    background:
      radial-gradient(1000px 600px at 15% 15%, rgba(122,167,255,.18), transparent 60%),
      radial-gradient(900px 600px at 85% 55%, rgba(255,122,214,.12), transparent 60%),
      var(--bg);
  }
  .topbar{
    position:sticky;top:0;z-index:10;
    display:flex;justify-content:space-between;align-items:center;
    padding:12px 14px;
    background:rgba(10,14,22,.60);backdrop-filter: blur(12px);
    border-bottom:1px solid rgba(255,255,255,.08);
  }
  .brand{font-weight:800;letter-spacing:.25px}
  .right{display:flex;gap:10px;align-items:center}
  .pill{
    padding:6px 10px;border-radius:999px;border:1px solid rgba(255,255,255,.10);
    background:rgba(13,20,36,.55);color:var(--muted);font-size:12px;
  }

  .wrap{max-width:1180px;margin:0 auto;padding:14px}
  .tabs{display:flex;gap:10px;align-items:center;margin:10px 0 14px}
  .tab{
    padding:10px 12px;border-radius:14px;border:1px solid rgba(255,255,255,.10);
    background:rgba(13,20,36,.55);cursor:pointer;user-select:none;
    transition:transform .12s ease, filter .12s ease, box-shadow .2s ease;
  }
  .tab:hover{transform:translateY(-1px);filter:brightness(1.08)}
  .tab.active{border-color:rgba(122,167,255,.75);box-shadow:0 0 0 3px rgba(122,167,255,.10) inset}

  .btn{
    padding:10px 12px;border-radius:12px;border:1px solid rgba(255,255,255,.10);
    background:rgba(27,39,66,.80);color:var(--text);cursor:pointer;
    transition:transform .12s ease, filter .12s ease;
  }
  .btn:hover{transform:translateY(-1px);filter:brightness(1.08)}
  .btn:active{transform:translateY(0px) scale(.99)}
  .btn.danger{border-color:rgba(255,122,122,.55)}
  .btn.ghost{background:rgba(13,20,36,.55)}

  .grid{display:grid;gap:12px}
  @media(min-width:980px){ .grid.two{grid-template-columns: 1.2fr 0.8fr;} }

  .card{
    background:var(--glass);
    border:1px solid rgba(255,255,255,.10);
    border-radius:18px;
    padding:14px;
    box-shadow:0 18px 60px rgba(0,0,0,.38);
    backdrop-filter: blur(14px);
    position:relative;
    overflow:hidden;
    transform:translateZ(0);
  }
  .card.stack:before{
    content:"";
    position:absolute;inset:-2px;
    background:linear-gradient(135deg, rgba(122,167,255,.30), rgba(255,122,214,.16), transparent 60%);
    filter:blur(18px);
    opacity:.75;
    pointer-events:none;
  }
  h2{margin:0 0 10px;font-size:16px;position:relative}
  .muted{color:var(--muted);font-size:13px;line-height:1.45;position:relative}
  input{
    width:100%;padding:10px 12px;border-radius:12px;border:1px solid rgba(255,255,255,.10);
    background:rgba(13,20,36,.72);color:var(--text);outline:none;
    transition:border-color .12s ease, box-shadow .12s ease;
  }
  input:focus{border-color:rgba(122,167,255,.65);box-shadow:0 0 0 3px rgba(122,167,255,.10)}
  .split{display:grid;gap:10px}
  @media(min-width:520px){ .split{grid-template-columns:1fr 1fr;} }

  .kpi{display:grid;gap:10px;margin-top:10px}
  @media(min-width:700px){ .kpi{grid-template-columns:repeat(3,1fr);} }
  .kbox{
    background:var(--glass2);border:1px solid rgba(255,255,255,.08);
    border-radius:16px;padding:12px;
    transition:transform .12s ease, filter .12s ease;
  }
  .kbox:hover{transform:translateY(-1px);filter:brightness(1.06)}
  .big{font-size:18px;font-weight:900}
  .badge{font-size:12px;color:var(--muted)}

  .tree{font-family:ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, "Liberation Mono","Courier New", monospace;font-size:13px}
  .node{
    padding:7px 9px;border-radius:12px;border:1px solid rgba(255,255,255,.08);
    background:rgba(13,20,36,.45);margin:7px 0;
    transition:transform .10s ease, filter .10s ease, border-color .10s ease;
  }
  .node:hover{transform:translateY(-1px);filter:brightness(1.08);border-color:rgba(122,167,255,.22)}
  .indent{margin-left:14px}
  .click{cursor:pointer}
  .ok{color:var(--ok)}
  .err{color:#ffb3b3}

  .panel{animation:fadeIn .16s ease both}
  @keyframes fadeIn{from{opacity:0;transform:translateY(4px)}to{opacity:1;transform:translateY(0)}}

  .toast{
    position:fixed;right:14px;bottom:14px;max-width:min(520px,92vw);
    background:rgba(13,20,36,.82);border:1px solid rgba(255,255,255,.10);
    border-radius:14px;padding:10px 12px;backdrop-filter: blur(14px);
    box-shadow:0 18px 60px rgba(0,0,0,.40);
    display:none;
  }
  .toast.show{display:block;animation:pop .16s ease both}
  @keyframes pop{from{opacity:0;transform:translateY(6px) scale(.99)}to{opacity:1;transform:translateY(0) scale(1)}}

  /* Progress */
  .progressWrap{
    margin-top:10px;
    padding:10px;
    border-radius:14px;
    border:1px solid rgba(255,255,255,.10);
    background:rgba(13,20,36,.50);
  }
  .barOuter{
    height:12px;border-radius:999px;background:rgba(255,255,255,.10);
    overflow:hidden;border:1px solid rgba(255,255,255,.10);
  }
  .barInner{
    height:100%;
    width:0%;
    border-radius:999px;
    background:linear-gradient(90deg, rgba(122,167,255,.85), rgba(255,122,214,.65));
    transition:width .18s ease;
  }
  .progRow{display:flex;justify-content:space-between;gap:10px;margin-top:8px;align-items:center}
  .mini{font-size:12px;color:var(--muted)}
  .pillMini{padding:4px 8px;border-radius:999px;border:1px solid rgba(255,255,255,.10);background:rgba(13,20,36,.55);font-size:12px;color:var(--muted)}
</style>
</head><body>
  <div class="topbar">
    <div class="brand">__TITLE__</div>
    <div class="right">
      <div class="pill">User: <b>__USERNAME__</b>__ADMIN_BADGE__</div>
      <button class="btn" onclick="logout()">Logout</button>
    </div>
  </div>

  <div class="wrap">
    <div class="tabs">
      <div class="tab active" id="tabFiles" onclick="showTab('files')">Files</div>
      <div class="tab" id="tabStats" onclick="showTab('stats')">Stats</div>
    </div>

    <div id="panelFiles" class="panel grid two">
      <div class="card stack">
        <h2>Browser</h2>
        <div class="muted">Click a file to download. Folder upload keeps subfolders. (Best in Chrome/Edge/Brave)</div>
        <div id="fileTree" class="tree" style="margin-top:10px"></div>
      </div>

      <div class="card stack">
        <h2>Actions</h2>

        <div class="muted">Upload into folder (optional):</div>
        <input id="uploadFolder" placeholder="e.g. projects/carrot_idle" style="margin-top:8px"/>

        <div class="split" style="margin-top:10px">
          <div>
            <div class="muted">Single file</div>
            <input id="uploadFile" type="file" style="margin-top:8px"/>
            <button class="btn" style="width:100%;margin-top:8px" onclick="uploadSingle()">Upload file</button>
          </div>
          <div>
            <div class="muted">Entire folder (chunked)</div>
            <input id="uploadDir" type="file" webkitdirectory directory multiple style="margin-top:8px"/>
            <div class="split" style="grid-template-columns: 1fr 1fr; margin-top:8px">
              <input id="chunkSize" type="number" min="10" max="500" value="120" title="Files per chunk"/>
              <button class="btn" onclick="uploadFolderChunked()">Upload folder</button>
            </div>

            <div class="progressWrap" id="progWrap" style="display:none">
              <div class="barOuter"><div class="barInner" id="progBar"></div></div>
              <div class="progRow">
                <div class="mini" id="progText">Preparing…</div>
                <div class="pillMini" id="progPill">0%</div>
              </div>
            </div>
          </div>
        </div>

        <div class="split" style="margin-top:12px">
          <div>
            <div class="muted">Create folder</div>
            <input id="mkdirPath" placeholder="e.g. notes/2025" style="margin-top:8px"/>
            <button class="btn ghost" style="width:100%;margin-top:8px" onclick="mkdir()">Create</button>
          </div>
          <div>
            <div class="muted">Delete (file or folder)</div>
            <input id="deletePath" placeholder="e.g. junk or temp.zip" style="margin-top:8px"/>
            <button class="btn danger" style="width:100%;margin-top:8px" onclick="del()">Delete</button>
          </div>
        </div>

        <div class="muted" style="margin-top:12px">Rename (path → new name)</div>
        <div class="split" style="margin-top:8px">
          <input id="renamePath" placeholder="e.g. old.txt or folderA"/>
          <input id="renameNew" placeholder="e.g. new.txt"/>
        </div>
        <button class="btn ghost" style="width:100%;margin-top:8px" onclick="rename()">Rename</button>

        <div class="muted" style="margin-top:12px" id="filesMsg"></div>
      </div>
    </div>

    <div id="panelStats" class="panel grid two" style="display:none">
      <div class="card stack">
        <h2>Storage</h2>
        <div class="muted">Your usage + disk usage.</div>
        <div class="kpi" id="storageKpi"></div>
      </div>

      <div class="card stack">
        __RIGHT_PANEL__
      </div>
    </div>
  </div>

  <div class="toast" id="toast"></div>

<script>
  function apiFetch(url, opts){
    opts = opts || {};
    opts.credentials = "include";
    return fetch(url, opts);
  }

  function escapeHtml(s){
    return String(s ?? "").replace(/[&<>"']/g, m => ({
      "&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#039;"
    }[m]));
  }

  function toast(msg, ok){
    const t = document.getElementById("toast");
    t.innerHTML = ok ? `<span class="ok">✅ ${escapeHtml(msg)}</span>` : `<span class="err">⚠ ${escapeHtml(msg)}</span>`;
    t.classList.add("show");
    clearTimeout(window.__toastTimer);
    window.__toastTimer = setTimeout(()=>t.classList.remove("show"), 2600);
  }

  function setProgress(show, pct, text){
    const wrap = document.getElementById("progWrap");
    const bar = document.getElementById("progBar");
    const pill = document.getElementById("progPill");
    const label = document.getElementById("progText");

    wrap.style.display = show ? "" : "none";
    if(!show) return;

    const p = Math.max(0, Math.min(100, pct||0));
    bar.style.width = p.toFixed(1) + "%";
    pill.textContent = Math.round(p) + "%";
    label.textContent = text || "";
  }

  async function logout(){
    await apiFetch("/logout", {method:"POST"});
    location.href="/login";
  }

  function setTab(which){
    document.getElementById("tabFiles").classList.toggle("active", which==="files");
    document.getElementById("tabStats").classList.toggle("active", which==="stats");
    document.getElementById("panelFiles").style.display = (which==="files") ? "" : "none";
    document.getElementById("panelStats").style.display = (which==="stats") ? "" : "none";
  }

  async function showTab(which){
    setTab(which);
    if(which==="files") await refreshTree();
    if(which==="stats") await refreshStorage();
  }

  async function refreshStorage(){
    const r = await apiFetch("/api/storage_stats");
    if(r.status===401){ location.href="/login"; return; }
    const data = await r.json();

    const el = document.getElementById("storageKpi");
    el.innerHTML = `
      <div class="kbox">
        <div class="badge">Your usage</div>
        <div class="big">${data.user.used_h}</div>
        <div class="badge">${data.user.files} files</div>
      </div>
      <div class="kbox">
        <div class="badge">Disk total</div>
        <div class="big">${data.disk.total_h}</div>
        <div class="badge">Free: ${data.disk.free_h}</div>
      </div>
      <div class="kbox">
        <div class="badge">Disk used</div>
        <div class="big">${data.disk.used_h}</div>
        <div class="badge">Overall used</div>
      </div>
    `;

    if(data.admin && data.admin.users){
      renderAdmin(data.admin.users);
    }
  }

  function renderAdmin(users){
    const wrap = document.getElementById("adminTable");
    if(!wrap) return;
    let html = `<div class="tree">`;
    html += `<div class="node"><b>Users:</b> ${users.length}</div>`;
    users.forEach(u=>{
      html += `<div class="node">
        <div><b>${escapeHtml(u.username)}</b> ${u.is_admin ? "• ADMIN" : ""}</div>
        <div class="badge">Used: ${u.used_h} • Files: ${u.files}</div>
      </div>`;
    });
    html += `</div>`;
    wrap.innerHTML = html;
  }

  async function refreshTree(){
    const r = await apiFetch("/api/file_tree");
    if(r.status===401){ location.href="/login"; return; }
    const tree = await r.json();
    document.getElementById("fileTree").innerHTML = renderTree(tree);
  }

  function renderTree(node){
    if(!node) return "";
    let html = "";
    if(node.type==="folder"){
      const label = node.path==="" ? "(root)" : node.name;
      html += `<div class="node"><span class="badge">📁</span> <b>${escapeHtml(label)}</b> <span class="badge">${escapeHtml(node.path)}</span></div>`;
      if(node.children && node.children.length){
        html += `<div class="indent">`;
        node.children.forEach(ch=>{ html += renderTree(ch); });
        html += `</div>`;
      }
    }else{
      const dl = `/download?p=${encodeURIComponent(node.path)}`;
      html += `<div class="node click" onclick="location.href='${dl}'">
        <span class="badge">📄</span> ${escapeHtml(node.name)}
        <span class="badge"> • ${fmtBytes(node.size)}</span>
      </div>`;
    }
    return html;
  }

  function fmtBytes(n){
    const units=["B","KB","MB","GB","TB"];
    let x=n; let i=0;
    while(x>=1024 && i<units.length-1){ x/=1024; i++; }
    return (i===0? Math.round(x) : x.toFixed(1))+" "+units[i];
  }

  async function uploadSingle(){
    const folder = document.getElementById("uploadFolder").value.trim();
    const f = document.getElementById("uploadFile").files[0];
    if(!f){ toast("Pick a file first.", false); return; }

    const form = new FormData();
    form.append("folder", folder);
    form.append("file", f);

    const r = await apiFetch("/api/upload", {method:"POST", body: form});
    if(r.status===401){ location.href="/login"; return; }
    let data=null; try{ data = await r.json(); }catch(e){}

    if(!r.ok){
      toast((data && data.msg) ? data.msg : ("Upload failed: HTTP " + r.status), false);
      return;
    }

    toast(data.msg || "Done.", true);
    refreshTree();
  }

  async function uploadFolderChunked(){
    const baseFolder = document.getElementById("uploadFolder").value.trim();
    const files = document.getElementById("uploadDir").files;
    if(!files || !files.length){ toast("Pick a folder first.", false); return; }

    // files per chunk
    let chunkSize = parseInt(document.getElementById("chunkSize").value || "120", 10);
    if(isNaN(chunkSize) || chunkSize < 10) chunkSize = 120;
    if(chunkSize > 500) chunkSize = 500;

    const totalFiles = files.length;
    const totalChunks = Math.ceil(totalFiles / chunkSize);

    setProgress(true, 0, `Starting… (${totalFiles} files, ${totalChunks} chunks)`);

    // IMPORTANT: sequential chunks (stable, less likely to die)
    let uploadedFiles = 0;

    for(let chunkIndex=0; chunkIndex<totalChunks; chunkIndex++){
      const start = chunkIndex * chunkSize;
      const end = Math.min(totalFiles, start + chunkSize);

      const form = new FormData();
      form.append("base_folder", baseFolder);
      form.append("chunk_index", String(chunkIndex));
      form.append("total_chunks", String(totalChunks));

      for(let i=start; i<end; i++){
        const f = files[i];
        form.append("files", f);
        form.append("paths", f.webkitRelativePath || f.name);
      }

      const pct = (uploadedFiles / totalFiles) * 100;
      setProgress(true, pct, `Uploading chunk ${chunkIndex+1}/${totalChunks} • files ${start+1}-${end} of ${totalFiles}`);

      const r = await apiFetch("/api/upload_folder_chunk", {method:"POST", body: form});
      if(r.status===401){ location.href="/login"; return; }

      let data=null; try{ data = await r.json(); }catch(e){}

      if(!r.ok){
        setProgress(false, 0, "");
        toast((data && data.msg) ? data.msg : ("Upload failed: HTTP " + r.status), false);
        return;
      }

      // server returns saved/skipped for this chunk
      uploadedFiles = end;

      const pct2 = (uploadedFiles / totalFiles) * 100;
      setProgress(true, pct2, `Chunk ${chunkIndex+1}/${totalChunks} done • ${uploadedFiles}/${totalFiles} files`);
    }

    setProgress(true, 100, "Finalizing…");
    await refreshTree();
    setTimeout(()=>setProgress(false, 0, ""), 700);

    toast("Folder uploaded successfully.", true);
  }

  async function mkdir(){
    const p = document.getElementById("mkdirPath").value.trim();
    if(!p){ toast("Type a folder path.", false); return; }

    const r = await apiFetch("/api/mkdir", {
      method:"POST",
      headers: {"Content-Type":"application/json"},
      body: JSON.stringify({path: p})
    });
    if(r.status===401){ location.href="/login"; return; }
    let data=null; try{ data = await r.json(); }catch(e){}

    if(!r.ok){
      toast((data && data.msg) ? data.msg : ("Failed: HTTP " + r.status), false);
      return;
    }

    toast(data.msg || "Created.", true);
    refreshTree();
  }

  async function rename(){
    const p = document.getElementById("renamePath").value.trim();
    const n = document.getElementById("renameNew").value.trim();
    if(!p || !n){ toast("Need path + new name.", false); return; }

    const r = await apiFetch("/api/rename", {
      method:"POST",
      headers: {"Content-Type":"application/json"},
      body: JSON.stringify({path: p, new_name: n})
    });
    if(r.status===401){ location.href="/login"; return; }
    let data=null; try{ data = await r.json(); }catch(e){}

    if(!r.ok){
      toast((data && data.msg) ? data.msg : ("Failed: HTTP " + r.status), false);
      return;
    }

    toast(data.msg || "Renamed.", true);
    refreshTree();
  }

  async function del(){
    const p = document.getElementById("deletePath").value.trim();
    if(!p){ toast("Type a path to delete.", false); return; }
    if(!confirm("Delete: "+p+" ? This cannot be undone.")) return;

    const r = await apiFetch("/api/delete", {
      method:"POST",
      headers: {"Content-Type":"application/json"},
      body: JSON.stringify({path: p})
    });
    if(r.status===401){ location.href="/login"; return; }
    let data=null; try{ data = await r.json(); }catch(e){}

    if(!r.ok){
      toast((data && data.msg) ? data.msg : ("Failed: HTTP " + r.status), false);
      return;
    }

    toast(data.msg || "Deleted.", true);
    refreshTree();
  }

  (async function boot(){
    await refreshTree();
  })();
</script>
</body></html>
"""

# ---------------- Routes ----------------

@app.route("/")
def root():
    return redirect("/app" if session.get("uid") else "/login")

@app.route("/login", methods=["GET", "POST"])
def login():
    msg = ""
    if request.method == "POST":
        username = (request.form.get("username") or "").strip()
        password = request.form.get("password") or ""

        conn = db()
        cur = conn.cursor()
        cur.execute("SELECT * FROM users WHERE username=?", (username,))
        u = cur.fetchone()
        conn.close()

        if not u or not check_password_hash(u["pass_hash"], password):
            msg = "Invalid username or password."
        else:
            session["uid"] = int(u["id"])
            return redirect("/app")

    html = LOGIN_HTML.replace("__TITLE__", APP_TITLE).replace("__MSG__", msg).replace("__ADMIN_USER__", DEFAULT_ADMIN_USERNAME)
    return html

@app.route("/register", methods=["GET", "POST"])
def register():
    msg = ""
    if request.method == "POST":
        username = (request.form.get("username") or "").strip()
        password = request.form.get("password") or ""

        if len(username) < 3 or len(username) > 24:
            msg = "Username must be 3–24 characters."
        elif len(password) < 6:
            msg = "Password must be at least 6 characters."
        else:
            conn = db()
            cur = conn.cursor()
            try:
                cur.execute(
                    "INSERT INTO users (username, pass_hash, is_admin, created_at) VALUES (?, ?, 0, ?)",
                    (username, generate_password_hash(password), int(time.time()))
                )
                conn.commit()
                cur.execute("SELECT id FROM users WHERE username=?", (username,))
                uid = int(cur.fetchone()["id"])
                conn.close()

                ensure_user_storage(uid)
                session["uid"] = uid
                return redirect("/app")
            except sqlite3.IntegrityError:
                conn.close()
                msg = "That username is taken."

    return REGISTER_HTML.replace("__TITLE__", APP_TITLE).replace("__MSG__", msg)

@app.route("/logout", methods=["POST"])
def logout():
    session.clear()
    return jsonify({"ok": True})

@app.route("/app")
def app_page():
    if not require_login():
        return redirect("/login")

    u = current_user()
    uid = int(u["id"])
    ensure_user_storage(uid)

    admin_badge = " • <b>ADMIN</b>" if int(u["is_admin"]) == 1 else ""

    if int(u["is_admin"]) == 1:
        right_panel = """
          <h2>Admin</h2>
          <div class="muted">All users storage usage.</div>
          <div id="adminTable" style="margin-top:10px"></div>
        """
    else:
        right_panel = """
          <h2>Tips</h2>
          <div class="muted">
            Folder upload is chunked now, so big folders don’t hang.<br/>
            If you still see 413, raise <code>MAX_UPLOAD_BYTES</code>.<br/>
            Best browser: Chrome/Edge/Brave (folder picker).
          </div>
        """

    html = APP_HTML
    html = html.replace("__TITLE__", APP_TITLE)
    html = html.replace("__USERNAME__", u["username"])
    html = html.replace("__ADMIN_BADGE__", admin_badge)
    html = html.replace("__RIGHT_PANEL__", right_panel)
    return html

# ---------------- API ----------------

@app.route("/api/storage_stats")
def api_storage_stats():
    if not require_login():
        return jsonify({"ok": False, "msg": "not logged in"}), 401

    u = current_user()
    uid = int(u["id"])
    rootp = user_root(uid)
    ensure_user_storage(uid)

    user_used = dir_size_bytes(rootp)
    user_files = count_files(rootp)
    ds = disk_stats()

    out = {
        "ok": True,
        "user": {"used": user_used, "used_h": fmt_bytes(user_used), "files": user_files},
        "disk": {
            "total": ds["total"], "total_h": fmt_bytes(ds["total"]),
            "used": ds["used"], "used_h": fmt_bytes(ds["used"]),
            "free": ds["free"], "free_h": fmt_bytes(ds["free"]),
        }
    }

    if int(u["is_admin"]) == 1:
        conn = db()
        cur = conn.cursor()
        cur.execute("SELECT id, username, is_admin FROM users ORDER BY is_admin DESC, username ASC")
        users = []
        for row in cur.fetchall():
            ruid = int(row["id"])
            rroot = user_root(ruid)
            os.makedirs(rroot, exist_ok=True)
            used = dir_size_bytes(rroot)
            files = count_files(rroot)
            users.append({
                "username": row["username"],
                "is_admin": bool(int(row["is_admin"]) == 1),
                "used_h": fmt_bytes(used),
                "files": files
            })
        conn.close()
        out["admin"] = {"users": users}

    return jsonify(out)

@app.route("/api/file_tree")
def api_file_tree():
    if not require_login():
        return jsonify({"ok": False, "msg": "not logged in"}), 401
    u = current_user()
    uid = int(u["id"])
    ensure_user_storage(uid)
    return jsonify(folder_tree(user_root(uid), ""))

@app.route("/download")
def download():
    if not require_login():
        return redirect("/login")

    u = current_user()
    uid = int(u["id"])
    rootp = user_root(uid)

    rel = request.args.get("p", "")
    try:
        abs_path = safe_join(rootp, rel)
    except ValueError:
        return "Invalid path", 400

    if not os.path.isfile(abs_path):
        return "Not found", 404

    folder = os.path.dirname(abs_path)
    filename = os.path.basename(abs_path)
    return send_from_directory(folder, filename, as_attachment=True)

@app.route("/api/upload", methods=["POST"])
def api_upload():
    if not require_login():
        return jsonify({"ok": False, "msg": "not logged in"}), 401

    u = current_user()
    uid = int(u["id"])
    rootp = user_root(uid)
    ensure_user_storage(uid)

    folder = sanitize_relpath((request.form.get("folder") or "").strip())
    f = request.files.get("file")
    if not f or not f.filename:
        return jsonify({"ok": False, "msg": "No file uploaded."})

    name = secure_filename(f.filename)
    if not name:
        return jsonify({"ok": False, "msg": "Bad filename."})

    try:
        target_dir = safe_join(rootp, folder)
        os.makedirs(target_dir, exist_ok=True)
        target_path = os.path.join(target_dir, name)
        f.save(target_path)
    except ValueError:
        return jsonify({"ok": False, "msg": "Invalid folder path."})
    except Exception as e:
        return jsonify({"ok": False, "msg": f"Upload failed: {e}"})

    return jsonify({"ok": True, "msg": f"Uploaded: {(folder or '(root)')} / {name}"})

@app.route("/api/upload_folder_chunk", methods=["POST"])
def api_upload_folder_chunk():
    """
    Chunk endpoint:
      form:
        base_folder (optional)
        chunk_index (optional, for UI)
        total_chunks (optional)
        files[] and paths[] (same length). paths[] = webkitRelativePath per file.
    """
    if not require_login():
        return jsonify({"ok": False, "msg": "not logged in"}), 401

    u = current_user()
    uid = int(u["id"])
    rootp = user_root(uid)
    ensure_user_storage(uid)

    base_folder = sanitize_relpath((request.form.get("base_folder") or "").strip())

    files = request.files.getlist("files")
    paths = request.form.getlist("paths")

    if not files:
        return jsonify({"ok": False, "msg": "No files received in chunk."}), 400

    if paths and len(paths) != len(files):
        return jsonify({"ok": False, "msg": "Upload mismatch (paths/files). Try again."}), 400

    saved = 0
    skipped = 0

    try:
        for i, f in enumerate(files):
            if not f or not f.filename:
                skipped += 1
                continue

            raw_rel = paths[i] if paths else f.filename
            rel = sanitize_relpath(raw_rel)  # keeps subfolders safely

            if base_folder:
                rel = f"{base_folder}/{rel}".strip("/")

            rel_dir = os.path.dirname(rel).replace("\\", "/")
            rel_name = os.path.basename(rel)

            rel_name = secure_filename(rel_name) or rel_name
            if not rel_name:
                skipped += 1
                continue

            target_dir = safe_join(rootp, rel_dir)
            os.makedirs(target_dir, exist_ok=True)

            target_path = os.path.join(target_dir, rel_name)
            f.save(target_path)
            saved += 1

    except ValueError:
        return jsonify({"ok": False, "msg": "Invalid path detected in upload."}), 400
    except Exception as e:
        return jsonify({"ok": False, "msg": f"Chunk upload failed: {e}"}), 500

    return jsonify({"ok": True, "msg": f"Chunk saved: {saved} files ({skipped} skipped)", "saved": saved, "skipped": skipped})

@app.route("/api/mkdir", methods=["POST"])
def api_mkdir():
    if not require_login():
        return jsonify({"ok": False, "msg": "not logged in"}), 401
    u = current_user()
    uid = int(u["id"])
    rootp = user_root(uid)

    data = request.get_json(force=True, silent=True) or {}
    p = sanitize_relpath((data.get("path") or "").strip())
    if not p:
        return jsonify({"ok": False, "msg": "Missing path."}), 400

    try:
        os.makedirs(safe_join(rootp, p), exist_ok=True)
    except ValueError:
        return jsonify({"ok": False, "msg": "Invalid path."}), 400
    except Exception as e:
        return jsonify({"ok": False, "msg": f"Failed: {e}"}), 500

    return jsonify({"ok": True, "msg": f"Folder created: {p}"})

@app.route("/api/delete", methods=["POST"])
def api_delete():
    if not require_login():
        return jsonify({"ok": False, "msg": "not logged in"}), 401
    u = current_user()
    uid = int(u["id"])
    rootp = user_root(uid)

    data = request.get_json(force=True, silent=True) or {}
    p = sanitize_relpath((data.get("path") or "").strip())
    if not p:
        return jsonify({"ok": False, "msg": "Missing path."}), 400

    try:
        abs_path = safe_join(rootp, p)
        if os.path.isdir(abs_path):
            shutil.rmtree(abs_path)
        elif os.path.isfile(abs_path):
            os.remove(abs_path)
        else:
            return jsonify({"ok": False, "msg": "Not found."}), 404
    except ValueError:
        return jsonify({"ok": False, "msg": "Invalid path."}), 400
    except Exception as e:
        return jsonify({"ok": False, "msg": f"Failed: {e}"}), 500

    return jsonify({"ok": True, "msg": f"Deleted: {p}"})

@app.route("/api/rename", methods=["POST"])
def api_rename():
    if not require_login():
        return jsonify({"ok": False, "msg": "not logged in"}), 401
    u = current_user()
    uid = int(u["id"])
    rootp = user_root(uid)

    data = request.get_json(force=True, silent=True) or {}
    p = sanitize_relpath((data.get("path") or "").strip())
    new_name = (data.get("new_name") or "").strip()

    if not p or not new_name:
        return jsonify({"ok": False, "msg": "Need path and new_name."}), 400

    try:
        abs_path = safe_join(rootp, p)
        parent = os.path.dirname(abs_path)

        base_new = new_name.replace("\\", "/").split("/")[-1].strip()
        safe_new = secure_filename(base_new) or base_new
        if not safe_new:
            return jsonify({"ok": False, "msg": "Bad new name."}), 400

        new_abs = os.path.join(parent, safe_new)

        if not os.path.exists(abs_path):
            return jsonify({"ok": False, "msg": "Not found."}), 404
        if os.path.exists(new_abs):
            return jsonify({"ok": False, "msg": "Target already exists."}), 409

        os.rename(abs_path, new_abs)
    except ValueError:
        return jsonify({"ok": False, "msg": "Invalid path."}), 400
    except Exception as e:
        return jsonify({"ok": False, "msg": f"Failed: {e}"}), 500

    return jsonify({"ok": True, "msg": f"Renamed to: {safe_new}"})

# ---------------- Main ----------------

if __name__ == "__main__":
    init_db()
    debug_mode = os.environ.get("FLASK_DEBUG", "false").lower() == "true"
    app.run(host=HOST, port=PORT, debug=debug_mode)
