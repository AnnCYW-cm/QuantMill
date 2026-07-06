#!/usr/bin/env bash
# =============================================================================
# build_pdf.sh —— 把项目文档(含 Mermaid UML)渲染成一本 PDF
# 输出:docs/quantmill-docs.pdf
# 依赖:python(markdown)、node/npm、curl。首次会装 puppeteer(下 Chromium,
#       约 150MB,全局缓存,仅一次)。之后秒级重生成。
# 用法:bash docs/build_pdf.sh   [--no-open 不自动打开]
# =============================================================================
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"          # 项目根
BUILD="$ROOT/docs/.pdfbuild"                       # 工作区(已 gitignore)
OUT="$ROOT/docs/quantmill-docs.pdf"
MERMAID_VER="11"
PY="$ROOT/.venv/bin/python"; [ -x "$PY" ] || PY="python3"
OPEN=1; [ "${1:-}" = "--no-open" ] && OPEN=0

mkdir -p "$BUILD"

# 1) mermaid.min.js(客户端渲染库)
if [ ! -s "$BUILD/mermaid.min.js" ]; then
  echo "· 拉取 mermaid.min.js…"
  curl -fsSL -o "$BUILD/mermaid.min.js" \
    "https://cdn.jsdelivr.net/npm/mermaid@${MERMAID_VER}/dist/mermaid.min.js"
fi

# 2) puppeteer(自带无头 Chromium)
if [ ! -d "$BUILD/node_modules/puppeteer" ]; then
  echo "· 首次安装 puppeteer(下 Chromium,约150MB,仅一次)…"
  ( cd "$BUILD" && npm init -y >/dev/null 2>&1 && npm i puppeteer >/dev/null 2>&1 )
fi

# 3) python markdown
$PY -c "import markdown" 2>/dev/null || { echo "· 安装 python markdown…"; $PY -m pip install -q markdown; }

# 4) 写出转换器(md -> 内联 mermaid 的 HTML)
cat > "$BUILD/build_html.py" <<'PYEOF'
# -*- coding: utf-8 -*-
import re, os, sys, markdown
ROOT, BUILD = sys.argv[1], sys.argv[2]
DOCS = [
    ("README.md", "README · 项目门面"),
    ("docs/ARCHITECTURE.md", "架构与 UML"),
    ("docs/RESEARCH_NOTES.md", "研究纪要"),
    ("docs/CLI.md", "CLI 命令参考"),
    ("docs/STATUS.md", "交付清单"),
]
mermaid_js = open(os.path.join(BUILD, "mermaid.min.js")).read()
blocks = []
def extract_mermaid(md):
    def repl(m):
        blocks.append(m.group(1)); return f"\n\nMMDPLACEHOLDER{len(blocks)-1}MMD\n\n"
    return re.sub(r"```mermaid\n(.*?)```", repl, md, flags=re.S)
parts = []
for path, title in DOCS:
    full = os.path.join(ROOT, path)
    if not os.path.exists(full):
        continue
    md = extract_mermaid(open(full).read())
    body = markdown.markdown(md, extensions=["fenced_code", "tables", "sane_lists"])
    def sub(m):
        src = (blocks[int(m.group(1))].replace("&", "&amp;")
               .replace("<", "&lt;").replace(">", "&gt;"))   # 转义,否则 <<abstract>> 坏图
        return f'<pre class="mermaid">{src}</pre>'
    body = re.sub(r"<p>MMDPLACEHOLDER(\d+)MMD</p>", sub, body)
    body = re.sub(r"MMDPLACEHOLDER(\d+)MMD", sub, body)
    parts.append(f'<section class="doc"><div class="banner">{title} · <code>{path}</code></div>{body}</section>')
CSS = """
* { box-sizing: border-box; }
body { font-family: -apple-system, "PingFang SC", "Helvetica Neue", Arial, sans-serif;
       color:#1a1d24; line-height:1.6; font-size:13px; margin:0; }
.doc { padding: 8px 4px 24px; page-break-after: always; }
.doc:last-child { page-break-after: auto; }
.banner { background:#12151b; color:#cbd5e1; padding:8px 12px; border-radius:6px;
          font-size:12px; margin:6px 0 16px; }
.banner code { color:#7dd3fc; }
h1 { font-size:22px; border-bottom:2px solid #e5e7eb; padding-bottom:6px; margin:22px 0 12px; }
h2 { font-size:17px; margin:20px 0 8px; color:#0f172a; }
h3 { font-size:14px; margin:16px 0 6px; color:#334155; }
p, li { font-size:13px; }
code { background:#f1f5f9; padding:1px 5px; border-radius:4px; font-size:12px;
       font-family:"SF Mono",Menlo,monospace; }
pre { background:#0f172a; color:#e2e8f0; padding:12px 14px; border-radius:8px;
      overflow-x:auto; font-size:11.5px; line-height:1.5; }
pre code { background:none; color:inherit; padding:0; }
table { border-collapse:collapse; width:100%; margin:10px 0; font-size:12px; }
th,td { border:1px solid #d1d5db; padding:5px 9px; text-align:left; vertical-align:top; }
th { background:#f8fafc; }
blockquote { border-left:4px solid #3b82f6; margin:10px 0; padding:4px 14px;
             background:#f0f7ff; color:#334155; border-radius:0 6px 6px 0; }
hr { border:none; border-top:1px solid #e5e7eb; margin:18px 0; }
a { color:#2563eb; text-decoration:none; }
pre.mermaid { background:#fff; border:1px solid #e5e7eb; padding:14px; text-align:center; }
pre.mermaid svg { max-width:100%; height:auto; }
"""
html = f"""<!doctype html><html lang="zh"><head><meta charset="utf-8">
<title>quantmill 文档</title><style>{CSS}</style>
<script>{mermaid_js}</script></head>
<body>
<div class="doc" style="page-break-after:always">
  <h1 style="font-size:30px;border:none;margin-top:40px">🏭 quantmill</h1>
  <div style="font-size:15px;color:#475569">开源全链条 AI 量化平台 · 项目文档合订本</div>
  <div style="font-size:12px;color:#94a3b8;margin-top:8px">README · 架构与UML · 研究纪要 · CLI参考 · 交付清单</div>
</div>
{''.join(parts)}
<script>
mermaid.initialize({{ startOnLoad:true, theme:'default', flowchart:{{useMaxWidth:true}},
  sequence:{{useMaxWidth:true}}, themeVariables:{{fontSize:'13px'}} }});
</script>
</body></html>"""
open(os.path.join(BUILD, "docs.html"), "w").write(html)
print(f"  HTML 就绪({len(blocks)} 张 mermaid 图)")
PYEOF

# 5) 写出渲染器(无头 Chromium 打印 PDF)
cat > "$BUILD/render.js" <<'JSEOF'
const puppeteer = require("puppeteer");
(async () => {
  const [htmlPath, pdfPath] = process.argv.slice(2);
  const browser = await puppeteer.launch({ headless: "new", args: ["--no-sandbox"] });
  const page = await browser.newPage();
  await page.goto("file://" + htmlPath, { waitUntil: "networkidle0", timeout: 90000 });
  await page.waitForFunction(() => {
    const all = document.querySelectorAll("pre.mermaid, .mermaid");
    if (all.length === 0) return true;
    return document.querySelectorAll("pre.mermaid > svg, .mermaid > svg").length >= all.length;
  }, { timeout: 90000 }).catch(() => console.log("  (mermaid 等待超时,继续打印)"));
  await new Promise(r => setTimeout(r, 1200));
  await page.pdf({ path: pdfPath, format: "A4", printBackground: true,
    margin: { top: "14mm", bottom: "14mm", left: "12mm", right: "12mm" } });
  await browser.close();
})().catch(e => { console.error("渲染失败:", e.message); process.exit(1); });
JSEOF

# 6) 生成
echo "· 生成 HTML…";  $PY "$BUILD/build_html.py" "$ROOT" "$BUILD"
echo "· 渲染 PDF…";   ( cd "$BUILD" && node render.js "$BUILD/docs.html" "$OUT" )
echo "✅ 完成 -> $OUT"
[ "$OPEN" = "1" ] && command -v open >/dev/null && open "$OUT" || true
