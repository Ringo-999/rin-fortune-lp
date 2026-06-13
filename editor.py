#!/usr/bin/env python3
"""りんLP スタジオエディター
使い方: python3 editor.py → http://localhost:7777 を開く
任意の要素をクリックで選択 → 右パネルで文字/色/サイズ/余白などを編集 →「保存」→「公開する🚀」
"""
import http.server, json, re, subprocess, os, shutil, datetime

ROOT = os.path.dirname(os.path.abspath(__file__))
INDEX = os.path.join(ROOT, "index.html")
PORT = 7777

EDITOR_JS = r"""
(function(){
  'use strict';
  const FX = [['','なし'],['fade-up','下から'],['fade-down','上から'],['fade-right','左から'],['fade-left','右から'],['zoom-in','ズーム'],['flip-up','フリップ']];
  const THEME_VARS = [['--bg','背景'],['--bg-2','背景2'],['--bordeaux','メイン'],['--bordeaux-2','メイン明'],['--wine','ワイン'],['--gold','ゴールド'],['--gold-2','ゴールド明'],['--paper','文字(明)'],['--text','本文']];
  let selected = null;
  const undoStack = [];

  /* ---------- chrome (html直下に置く=body復元で消えない) ---------- */
  const style = document.createElement('style');
  style.id = 'rin-style';
  style.textContent = `
    #rin-bar{position:fixed;bottom:22px;left:22px;z-index:99999;display:flex;gap:10px;align-items:center;
      background:#160f11;border:1px solid #d4af6a;border-radius:14px;padding:12px 16px;
      font-family:'Noto Sans JP',sans-serif;font-size:13px;color:#efe6dc;box-shadow:0 18px 50px rgba(0,0,0,.6)}
    #rin-bar button{border:none;border-radius:9px;padding:9px 16px;font-size:13px;cursor:pointer;font-family:inherit;transition:.2s}
    #rin-bar .ghost{background:#2a1d20;color:#efe6dc;border:1px solid rgba(212,175,106,.4)}
    #rin-bar .ghost:hover{background:#3a282c}
    #rin-bar #rin-save{background:#d4af6a;color:#160f11;font-weight:700}
    #rin-bar #rin-save:hover{background:#f0d9a8}
    #rin-bar #rin-deploy{background:#6e1423;color:#fff;font-weight:700}
    #rin-bar #rin-deploy:hover{background:#9b2237}
    #rin-status{min-width:120px;opacity:.85;font-size:12px}
    #rin-panel{position:fixed;top:0;right:0;width:300px;height:100vh;z-index:99998;overflow-y:auto;
      background:#160f11;border-left:1px solid #d4af6a;color:#efe6dc;font-family:'Noto Sans JP',sans-serif;
      transform:translateX(310px);transition:transform .25s;padding:18px 18px 120px}
    #rin-panel.open{transform:none}
    #rin-panel h4{font-size:12px;letter-spacing:.15em;color:#d4af6a;margin:18px 0 8px;border-bottom:1px solid rgba(212,175,106,.25);padding-bottom:5px}
    #rin-panel h4:first-child{margin-top:0}
    #rin-panel .tag{font-size:11px;color:#9b8;opacity:.8;margin-bottom:6px;word-break:break-all}
    .rin-row{display:flex;align-items:center;justify-content:space-between;gap:8px;margin:7px 0;font-size:12px}
    .rin-row label{opacity:.85;white-space:nowrap}
    .rin-row input[type=range]{flex:1;accent-color:#d4af6a}
    .rin-row input[type=color]{width:34px;height:26px;border:1px solid rgba(212,175,106,.4);border-radius:6px;background:none;padding:0;cursor:pointer}
    .rin-row input[type=number],.rin-row select{background:#2a1d20;color:#efe6dc;border:1px solid rgba(212,175,106,.4);border-radius:6px;padding:5px 7px;font-size:12px;width:80px;font-family:inherit}
    .rin-num{width:46px!important;text-align:right}
    .rin-btns{display:flex;flex-wrap:wrap;gap:6px;margin-top:8px}
    .rin-btns button{flex:1;min-width:62px;background:#2a1d20;color:#efe6dc;border:1px solid rgba(212,175,106,.4);
      border-radius:8px;padding:8px 4px;font-size:12px;cursor:pointer;font-family:inherit;transition:.2s}
    .rin-btns button:hover{background:#6e1423}
    .rin-align button{flex:1}
    .rin-hint{font-size:11px;opacity:.55;line-height:1.7;margin-top:4px}
    .rin-sel-outline{outline:2px solid #d4af6a!important;outline-offset:2px}
    .rin-hover-outline{outline:1px dashed rgba(212,175,106,.55)!important}
    .rin-hide-mark{opacity:.3;filter:grayscale(1)}
    [data-rin-edit]:hover{cursor:text}
  `;
  document.documentElement.appendChild(style);

  /* ---------- toolbar ---------- */
  const bar = document.createElement('div');
  bar.id = 'rin-bar';
  bar.innerHTML = `
    <strong style="color:#d4af6a">りん Studio</strong>
    <button class="ghost" id="rin-undo">↩ 戻す</button>
    <button class="ghost" id="rin-theme">🎨 テーマ</button>
    <button id="rin-save">保存</button>
    <button id="rin-deploy">公開する 🚀</button>
    <span id="rin-status">要素をクリックで選択</span>`;
  document.documentElement.appendChild(bar);
  const status = bar.querySelector('#rin-status');
  const setStatus = t => status.textContent = t;

  /* ---------- inspector panel ---------- */
  const panel = document.createElement('div');
  panel.id = 'rin-panel';
  document.documentElement.appendChild(panel);

  /* ---------- file picker (画像) ---------- */
  const picker = document.createElement('input');
  picker.type='file'; picker.accept='image/jpeg,image/png,image/webp'; picker.style.display='none';
  document.documentElement.appendChild(picker);
  let imgTarget=null;
  picker.onchange = async () => {
    const f=picker.files[0]; if(!f||!imgTarget) return;
    if(f.size>8*1024*1024){setStatus('❌ 8MB以下に');return;}
    const name=(imgTarget.getAttribute('src')||'').split('?')[0].split('/').pop()||('img-'+Date.now()+'.jpg');
    setStatus('画像アップ中…');
    try{
      const r=await fetch('/upload?name='+encodeURIComponent(name),{method:'POST',body:f});
      const j=await r.json();
      if(j.ok){imgTarget.src=j.name+'?v='+Date.now();setStatus('✅ 画像差替＆保存');}
      else setStatus('❌ '+j.error);
    }catch(e){setStatus('❌ アップ失敗');}
  };

  /* ---------- helpers ---------- */
  const isChrome = el => el.closest('#rin-bar,#rin-panel,#rin-style');
  const px = v => Math.round(parseFloat(v)||0);
  const cs = el => getComputedStyle(el);
  const rgb2hex = c => {
    const m=c.match(/\d+/g); if(!m) return '#000000';
    return '#'+m.slice(0,3).map(x=>(+x).toString(16).padStart(2,'0')).join('');
  };

  function getCleanBody(){
    const b=document.body.cloneNode(true);
    b.querySelectorAll('.rin-sel-outline,.rin-hover-outline').forEach(n=>n.classList.remove('rin-sel-outline','rin-hover-outline'));
    return b.innerHTML;
  }
  function pushUndo(){
    undoStack.push({body:getCleanBody(), html:document.documentElement.getAttribute('style')||''});
    if(undoStack.length>40) undoStack.shift();
  }

  /* ---------- selection ---------- */
  let hoverEl=null;
  document.addEventListener('mouseover', e=>{
    if(isChrome(e.target)) return;
    if(hoverEl) hoverEl.classList.remove('rin-hover-outline');
    hoverEl=e.target; if(hoverEl!==selected) hoverEl.classList.add('rin-hover-outline');
  });
  document.addEventListener('mouseout', e=>{ if(hoverEl){hoverEl.classList.remove('rin-hover-outline');hoverEl=null;} });

  document.addEventListener('click', e=>{
    if(isChrome(e.target)) return;
    const a=e.target.closest('a'); if(a) e.preventDefault();
    if(e.target===document.body||e.target===document.documentElement) return;
    select(e.target);
  }, true);

  function select(el){
    if(selected) selected.classList.remove('rin-sel-outline');
    selected=el; el.classList.remove('rin-hover-outline'); el.classList.add('rin-sel-outline');
    renderInspector(el);
    panel.classList.add('open');
  }

  /* ---------- inspector UI ---------- */
  function row(label, control){ return `<div class="rin-row"><label>${label}</label>${control}</div>`; }

  function renderInspector(el){
    const c=cs(el);
    const hasText = [...el.childNodes].some(n=>n.nodeType===3 && n.textContent.trim());
    const isImg = el.tagName==='IMG';
    const isSection = el.matches('section,div.marquee');
    const aosEl = el.hasAttribute('data-aos') ? el : (isSection ? el.querySelector('[data-aos]') : null);
    const tagName = el.tagName.toLowerCase()+(el.className?('.'+[...el.classList].filter(x=>!x.startsWith('rin-')).join('.')):'');

    let html = `<div class="tag">▣ ${tagName}</div>`;

    if(hasText){
      html += `<h4>テキスト</h4>`;
      html += row('色', `<input type="color" id="ri-color" value="${rgb2hex(c.color)}">`);
      html += row('サイズ', `<input type="range" id="ri-fs" min="8" max="120" value="${px(c.fontSize)}"><input type="number" class="rin-num" id="ri-fsn" value="${px(c.fontSize)}">`);
      html += row('太さ', `<select id="ri-fw">${[300,400,500,600,700,900].map(w=>`<option ${px(c.fontWeight)===w?'selected':''}>${w}</option>`).join('')}</select>`);
      html += row('行間', `<input type="range" id="ri-lh" min="1" max="3" step="0.05" value="${(parseFloat(c.lineHeight)/px(c.fontSize)||1.5).toFixed(2)}">`);
      html += row('字間(px)', `<input type="range" id="ri-ls" min="-2" max="20" step="0.5" value="${px(c.letterSpacing)||0}">`);
      html += `<div class="rin-btns rin-align">
        <button data-al="left">左</button><button data-al="center">中央</button><button data-al="right">右</button></div>`;
    }

    html += `<h4>背景・枠</h4>`;
    html += row('背景色', `<input type="color" id="ri-bg" value="${rgb2hex(c.backgroundColor)}"><button class="ghost" id="ri-bgclear" style="padding:4px 8px;font-size:11px;border-radius:6px">透明</button>`);
    html += row('角丸(px)', `<input type="range" id="ri-br" min="0" max="80" value="${px(c.borderRadius)}">`);
    html += row('透明度', `<input type="range" id="ri-op" min="0" max="1" step="0.05" value="${c.opacity}">`);

    html += `<h4>余白</h4>`;
    html += row('内側(px)', `<input type="range" id="ri-pad" min="0" max="160" value="${px(c.paddingTop)}">`);
    html += row('外側(px)', `<input type="range" id="ri-mar" min="0" max="160" value="${px(c.marginTop)}">`);

    if(aosEl){
      html += `<h4>アニメーション</h4>`;
      html += row('効果', `<select id="ri-fx">${FX.map(([v,l])=>`<option value="${v}" ${aosEl.getAttribute('data-aos')===v?'selected':''}>🎬 ${l}</option>`).join('')}</select>`);
    }

    html += `<h4>操作</h4>`;
    html += `<div class="rin-btns">`;
    if(isImg) html += `<button id="ri-img">🖼 画像差替</button>`;
    if(isSection) html += `<button id="ri-up">↑ 上へ</button><button id="ri-down">↓ 下へ</button><button id="ri-hide">👁 表示切替</button>`;
    html += `<button id="ri-dup">⧉ 複製</button><button id="ri-del">🗑 削除</button></div>`;
    html += `<p class="rin-hint">文字は要素を直接クリックしても打ち替えられます。Esc で選択解除。</p>`;

    panel.innerHTML = html;
    bindInspector(el, aosEl, isImg, isSection);
  }

  function bindInspector(el, aosEl, isImg, isSection){
    const $=id=>panel.querySelector('#'+id);
    const live=(id,ev,fn)=>{const e=$(id); if(e) e.addEventListener(ev,fn);};
    const commitOnce=(id)=>{const e=$(id); if(e) e.addEventListener('change',()=>{},{once:true});};

    // typography
    live('ri-color','input',e=>{el.style.color=e.target.value;});
    live('ri-color','change',pushUndo);
    const fs=$('ri-fs'),fsn=$('ri-fsn');
    if(fs){fs.addEventListener('input',e=>{el.style.fontSize=e.target.value+'px';if(fsn)fsn.value=e.target.value;});fs.addEventListener('change',pushUndo);}
    if(fsn){fsn.addEventListener('input',e=>{el.style.fontSize=e.target.value+'px';if(fs)fs.value=e.target.value;});}
    live('ri-fw','change',e=>{pushUndo();el.style.fontWeight=e.target.value;});
    live('ri-lh','input',e=>{el.style.lineHeight=e.target.value;});
    live('ri-lh','change',pushUndo);
    live('ri-ls','input',e=>{el.style.letterSpacing=e.target.value+'px';});
    live('ri-ls','change',pushUndo);
    panel.querySelectorAll('.rin-align button').forEach(b=>b.onclick=()=>{pushUndo();el.style.textAlign=b.dataset.al;});

    // bg / border
    live('ri-bg','input',e=>{el.style.backgroundColor=e.target.value;});
    live('ri-bg','change',pushUndo);
    live('ri-bgclear','click',()=>{pushUndo();el.style.backgroundColor='transparent';});
    live('ri-br','input',e=>{el.style.borderRadius=e.target.value+'px';});
    live('ri-br','change',pushUndo);
    live('ri-op','input',e=>{el.style.opacity=e.target.value;});
    live('ri-op','change',pushUndo);

    // spacing
    live('ri-pad','input',e=>{el.style.padding=e.target.value+'px';});
    live('ri-pad','change',pushUndo);
    live('ri-mar','input',e=>{el.style.margin=e.target.value+'px';});
    live('ri-mar','change',pushUndo);

    // animation
    live('ri-fx','change',e=>{
      pushUndo();
      const targets = isSection ? el.querySelectorAll('[data-aos]') : [aosEl];
      targets.forEach(t=>{ if(!t)return; if(e.target.value){t.setAttribute('data-aos',e.target.value);}else{t.removeAttribute('data-aos');} t.classList.remove('aos-init','aos-animate'); });
      if(window.AOS) AOS.refreshHard();
      setStatus('✅ アニメ変更');
    });

    // actions
    live('ri-img','click',()=>{imgTarget=el;picker.value='';picker.click();});
    live('ri-up','click',()=>{pushUndo();const p=el.previousElementSibling;if(p&&p.matches('section,div.marquee'))el.parentNode.insertBefore(el,p);el.scrollIntoView({behavior:'smooth',block:'center'});});
    live('ri-down','click',()=>{pushUndo();const n=el.nextElementSibling;if(n&&n.matches('section,div.marquee'))el.parentNode.insertBefore(n,el);el.scrollIntoView({behavior:'smooth',block:'center'});});
    live('ri-hide','click',()=>{pushUndo();const h=el.classList.toggle('rin-hide-mark');if(h)el.setAttribute('data-rin-hide','1');else el.removeAttribute('data-rin-hide');setStatus(h?'公開時に非表示':'表示に戻す');});
    live('ri-dup','click',()=>{pushUndo();const cl=el.cloneNode(true);cl.classList.remove('rin-sel-outline');el.after(cl);setStatus('⧉ 複製しました');});
    live('ri-del','click',()=>{pushUndo();el.remove();selected=null;panel.classList.remove('open');setStatus('🗑 削除しました');});
  }

  /* ---------- theme panel ---------- */
  let themeOpen=false;
  bar.querySelector('#rin-theme').onclick=()=>{
    themeOpen=!themeOpen;
    if(!themeOpen){panel.classList.remove('open');return;}
    const rootCS=cs(document.documentElement);
    let html=`<div class="tag">🎨 テーマカラー（サイト全体）</div>`;
    THEME_VARS.forEach(([v,l])=>{
      const cur=(document.documentElement.style.getPropertyValue(v)||rootCS.getPropertyValue(v)).trim();
      const hex=cur.startsWith('#')?cur:rgb2hex(cur);
      html+=row(l,`<input type="color" data-var="${v}" value="${hex}">`);
    });
    html+=`<p class="rin-hint">色を変えると全ページに即反映されます。</p>`;
    panel.innerHTML=html; panel.classList.add('open');
    panel.querySelectorAll('input[data-var]').forEach(inp=>{
      inp.addEventListener('input',e=>document.documentElement.style.setProperty(e.target.dataset.var,e.target.value));
      inp.addEventListener('change',pushUndo);
    });
  };

  /* ---------- undo ---------- */
  bar.querySelector('#rin-undo').onclick=doUndo;
  document.addEventListener('keydown',e=>{
    if((e.metaKey||e.ctrlKey)&&e.key==='z'){e.preventDefault();doUndo();}
    if(e.key==='Escape'&&selected){selected.classList.remove('rin-sel-outline');selected=null;panel.classList.remove('open');}
  });
  function doUndo(){
    if(!undoStack.length){setStatus('これ以上戻せません');return;}
    const s=undoStack.pop();
    document.body.innerHTML=s.body;
    if(s.html) document.documentElement.setAttribute('style',s.html); else document.documentElement.removeAttribute('style');
    selected=null; panel.classList.remove('open');
    if(window.AOS) AOS.refreshHard();
    setStatus('↩ 戻しました');
  }

  /* ---------- save / deploy ---------- */
  function cleanHTML(){
    const doc=document.documentElement.cloneNode(true);
    doc.querySelectorAll('#rin-bar,#rin-panel,#rin-style,script[data-rin-editor]').forEach(n=>n.remove());
    doc.querySelectorAll('.rin-sel-outline,.rin-hover-outline').forEach(n=>n.classList.remove('rin-sel-outline','rin-hover-outline'));
    doc.querySelectorAll('.aos-init,.aos-animate').forEach(n=>n.classList.remove('aos-init','aos-animate'));
    doc.querySelectorAll('[data-aos]').forEach(n=>n.removeAttribute('style')); // aos由来のinline opacityを除去 ※後で本来styleは無いので安全
    doc.querySelectorAll('img').forEach(n=>{n.removeAttribute('title');const s=n.getAttribute('src');if(s)n.setAttribute('src',s.split('?')[0]);});
    // 非表示指定 → display:none で永続化
    doc.querySelectorAll('[data-rin-hide]').forEach(n=>{n.removeAttribute('data-rin-hide');n.classList.remove('rin-hide-mark');n.style.display='none';});
    doc.querySelectorAll('.rin-hide-mark').forEach(n=>n.classList.remove('rin-hide-mark'));
    doc.querySelectorAll('[class=""]').forEach(n=>n.removeAttribute('class'));
    return '<!DOCTYPE html>\n'+doc.outerHTML;
  }
  async function post(url){
    setStatus(url==='/save'?'保存中…':'公開中…(約1分)');
    try{
      const r=await fetch(url,{method:'POST',headers:{'Content-Type':'text/html'},body:cleanHTML()});
      const j=await r.json();
      setStatus(j.ok?(url==='/save'?'✅ 保存しました':'✅ 公開しました！'):'❌ '+j.error);
    }catch(e){setStatus('❌ 通信エラー');}
  }
  bar.querySelector('#rin-save').onclick=()=>post('/save');
  bar.querySelector('#rin-deploy').onclick=()=>post('/deploy');

  /* ---------- 直接テキスト編集を有効化 ---------- */
  function enableText(){
    document.querySelectorAll('h1,h2,h3,h4,h5,p,span,a,li,td,small,button,div').forEach(el=>{
      if(isChrome(el)) return;
      const direct=[...el.childNodes].some(n=>n.nodeType===3&&n.textContent.trim());
      if(direct&&el.children.length<=2){el.setAttribute('data-rin-edit','1');el.setAttribute('contenteditable','plaintext-only');}
    });
  }
  enableText();
  // contenteditableで打った内容はDOMに反映済み→保存時にcleanHTMLで属性除去される
})();
"""

# NOTE: contenteditable/data-rin-edit 属性は cleanHTML 内で除去する（下のJS追補で対応）
EDITOR_JS = EDITOR_JS.replace(
    "doc.querySelectorAll('[class=\"\"]').forEach(n=>n.removeAttribute('class'));",
    "doc.querySelectorAll('[contenteditable]').forEach(n=>n.removeAttribute('contenteditable'));\n"
    "    doc.querySelectorAll('[data-rin-edit]').forEach(n=>n.removeAttribute('data-rin-edit'));\n"
    "    doc.querySelectorAll('[class=\"\"]').forEach(n=>n.removeAttribute('class'));"
)


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
        elif re.fullmatch(r"/[\w-]+\.(jpg|jpeg|png|webp)", path):
            ctype = {"png": "image/png", "webp": "image/webp"}.get(path.rsplit(".", 1)[1], "image/jpeg")
            try:
                self._send(200, open(os.path.join(ROOT, path[1:]), "rb").read(), ctype)
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
        ts = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
        os.makedirs(os.path.join(ROOT, ".backups"), exist_ok=True)
        shutil.copy(INDEX, os.path.join(ROOT, ".backups", f"index-{ts}.html"))
        with open(INDEX, "w", encoding="utf-8") as f:
            f.write(html)
        return True, None

    def do_POST(self):
        if self.path.startswith("/upload"):
            from urllib.parse import urlparse, parse_qs
            name = parse_qs(urlparse(self.path).query).get("name", [""])[0]
            if not re.fullmatch(r"[\w-]+\.(jpg|jpeg|png|webp)", name):
                self._send(200, json.dumps({"ok": False, "error": "ファイル名が不正です"}), "application/json")
                return
            data = self.rfile.read(int(self.headers.get("Content-Length", 0)))
            if len(data) < 100 or len(data) > 8 * 1024 * 1024:
                self._send(200, json.dumps({"ok": False, "error": "サイズが不正です"}), "application/json")
                return
            dest = os.path.join(ROOT, name)
            if os.path.exists(dest):
                ts = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
                os.makedirs(os.path.join(ROOT, ".backups"), exist_ok=True)
                shutil.copy(dest, os.path.join(ROOT, ".backups", f"{ts}-{name}"))
            with open(dest, "wb") as f:
                f.write(data)
            self._send(200, json.dumps({"ok": True, "name": name}), "application/json")
        elif self.path == "/save":
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
                                        "commit", "-m", "スタジオ編集 (editor)", "-q"], cwd=ROOT, capture_output=True)
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
    print(f"🎨 りん Studio エディター起動: http://localhost:{PORT}")
    print("   要素をクリックで選択 → 右パネルで編集 →「保存」→「公開する🚀」")
    http.server.ThreadingHTTPServer(("127.0.0.1", PORT), Handler).serve_forever()
