#!/usr/bin/env python3
"""りんLP テキスト編集ツール (Wix風)
使い方: python3 editor.py → http://localhost:7777 を開く
クリックで文字を編集 → 「保存」でindex.htmlに書き込み → 「公開」でVercelへデプロイ
"""
import http.server, json, re, subprocess, os, shutil, datetime

ROOT = os.path.dirname(os.path.abspath(__file__))
INDEX = os.path.join(ROOT, "index.html")
PORT = 7777

EDITOR_JS = r"""
(function(){
  // 編集対象: テキストを持つ要素
  const SEL = 'h1,h2,h3,p,span,a,li,td,small,div.num,div.label,div.no,div.fee,div.p-name';
  document.querySelectorAll(SEL).forEach(el => {
    if (el.closest('#rin-editor-bar')) return;
    if (el.children.length > 0 && [...el.childNodes].every(n => n.nodeType !== 3 || !n.textContent.trim())) return;
    el.setAttribute('contenteditable','true');
    el.classList.add('rin-editable');
  });
  // リンクのクリック遷移を無効化(編集優先)
  document.addEventListener('click', e => {
    const a = e.target.closest('a');
    if (a && !a.closest('#rin-editor-bar')) e.preventDefault();
  }, true);

  const style = document.createElement('style');
  style.id = 'rin-editor-style';
  style.textContent = `
    .rin-editable{outline:1px dashed rgba(212,175,106,.0);transition:outline-color .2s;cursor:text}
    .rin-editable:hover{outline-color:rgba(212,175,106,.6)}
    .rin-editable:focus{outline:2px solid #d4af6a;outline-offset:2px;background:rgba(212,175,106,.08)}
    #rin-editor-bar{position:fixed;bottom:24px;left:50%;transform:translateX(-50%);z-index:99999;
      display:flex;gap:12px;align-items:center;background:#1c1416;border:1px solid #d4af6a;
      border-radius:999px;padding:12px 22px;box-shadow:0 16px 50px rgba(0,0,0,.6);
      font-family:'Noto Sans JP',sans-serif;font-size:13px;color:#efe6dc}
    #rin-editor-bar button{border:none;border-radius:999px;padding:10px 26px;font-size:13px;
      letter-spacing:.1em;cursor:pointer;font-family:inherit;transition:.25s}
    #rin-save{background:#d4af6a;color:#1c1416;font-weight:700}
    #rin-save:hover{background:#f0d9a8}
    #rin-deploy{background:#6e1423;color:#fff;font-weight:700}
    #rin-deploy:hover{background:#9b2237}
    #rin-status{min-width:130px;opacity:.85}
  `;
  document.head.appendChild(style);

  const bar = document.createElement('div');
  bar.id = 'rin-editor-bar';
  bar.innerHTML = `<span>✏️ 編集モード</span>
    <button id="rin-save">保存</button>
    <button id="rin-deploy">公開する 🚀</button>
    <span id="rin-status">文字をクリックして編集</span>`;
  document.body.appendChild(bar);
  const status = bar.querySelector('#rin-status');

  function cleanHTML(){
    const doc = document.documentElement.cloneNode(true);
    doc.querySelectorAll('#rin-editor-bar,#rin-editor-style,script[data-rin-editor]').forEach(n=>n.remove());
    doc.querySelectorAll('[contenteditable]').forEach(n=>{n.removeAttribute('contenteditable');n.classList.remove('rin-editable');if(!n.classList.length)n.removeAttribute('class');});
    doc.querySelectorAll('.aos-init,.aos-animate').forEach(n=>n.classList.remove('aos-init','aos-animate'));
    doc.querySelectorAll('[data-aos]').forEach(n=>{n.removeAttribute('style')});
    doc.querySelectorAll('body').forEach(b=>b.removeAttribute('style'));
    return '<!DOCTYPE html>\n' + doc.outerHTML;
  }
  async function post(url){
    status.textContent = url === '/save' ? '保存中…' : '公開中…(1分ほど)';
    try{
      const r = await fetch(url,{method:'POST',headers:{'Content-Type':'text/html'},body:cleanHTML()});
      const j = await r.json();
      status.textContent = j.ok ? (url==='/save' ? '✅ 保存しました' : '✅ 公開しました！') : '❌ ' + j.error;
    }catch(e){ status.textContent = '❌ 通信エラー'; }
  }
  bar.querySelector('#rin-save').onclick = ()=>post('/save');
  bar.querySelector('#rin-deploy').onclick = ()=>post('/deploy');
})();
"""

def vercel_path():
    for p in ("/opt/homebrew/bin/vercel", shutil.which("vercel")):
        if p and os.path.exists(p): return p
    return None

class Handler(http.server.BaseHTTPRequestHandler):
    def log_message(self, *a): pass

    def _send(self, code, body, ctype="text/html; charset=utf-8"):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body if isinstance(body, bytes) else body.encode())

    def do_GET(self):
        path = self.path.split("?")[0]
        if path == "/":
            html = open(INDEX, encoding="utf-8").read()
            inject = f'<script data-rin-editor>{EDITOR_JS}</script></body>'
            html = html.replace("</body>", inject)
            self._send(200, html)
        elif path in ("/rin.jpg", "/hero.jpg"):
            try:
                self._send(200, open(os.path.join(ROOT, path[1:]), "rb").read(), "image/jpeg")
            except FileNotFoundError:
                self._send(404, "not found")
        else:
            self._send(404, "not found")

    def _read_body(self):
        n = int(self.headers.get("Content-Length", 0))
        return self.rfile.read(n).decode("utf-8")

    def _save(self):
        html = self._read_body()
        if "</html>" not in html or len(html) < 1000:
            return False, "内容が不正です"
        # バックアップしてから書き込み
        ts = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
        os.makedirs(os.path.join(ROOT, ".backups"), exist_ok=True)
        shutil.copy(INDEX, os.path.join(ROOT, ".backups", f"index-{ts}.html"))
        with open(INDEX, "w", encoding="utf-8") as f:
            f.write(html)
        return True, None

    def do_POST(self):
        if self.path == "/save":
            ok, err = self._save()
            self._send(200, json.dumps({"ok": ok, "error": err}), "application/json")
        elif self.path == "/deploy":
            ok, err = self._save()
            if ok:
                vc = vercel_path()
                if not vc:
                    ok, err = False, "vercel CLIが見つかりません"
                else:
                    try:
                        subprocess.run(["git", "add", "-A"], cwd=ROOT, check=True, capture_output=True)
                        subprocess.run(["git", "-c", "user.name=rin", "-c", "user.email=yoshikosumosu.y@gmail.com",
                                        "commit", "-m", "テキスト編集 (editor)", "-q"], cwd=ROOT, capture_output=True)
                        subprocess.run(["git", "push", "-q", "origin", "main"], cwd=ROOT, capture_output=True)
                        r = subprocess.run([vc, "deploy", "--prod", "--yes"], cwd=ROOT,
                                           capture_output=True, text=True, timeout=240)
                        if r.returncode != 0:
                            ok, err = False, "デプロイ失敗: " + (r.stderr or r.stdout)[-200:]
                    except Exception as e:
                        ok, err = False, str(e)
            self._send(200, json.dumps({"ok": ok, "error": err}), "application/json")
        else:
            self._send(404, "not found")

if __name__ == "__main__":
    print(f"✏️  編集モード起動: http://localhost:{PORT}")
    print("   文字をクリックして編集 →「保存」→「公開する🚀」")
    http.server.ThreadingHTTPServer(("127.0.0.1", PORT), Handler).serve_forever()
