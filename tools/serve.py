#!/usr/bin/env python3
"""Local preview of the captured documentation.

Serves content/ at the live paths (/rodec-one, /rodec-m-110-sidestepper/presets, ...)
and assets/ at /assets, so internal links work exactly as on the live site.
A plain menu (from site.json) and the footer are injected for browsing; the
files on disk are not changed.

Usage:  python3 tools/serve.py [port]     (default 8000)
"""
import html
import json
import sys
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse, unquote

ROOT = Path(__file__).resolve().parent.parent
SITE = json.loads((ROOT / "site.json").read_text())
FOOTER = (ROOT / "content" / "_footer.html").read_text() if (ROOT / "content" / "_footer.html").exists() else ""

STYLE = """<style>
body{margin:0;font:16px/1.55 system-ui,sans-serif;color:#1a1a1a;display:flex}
#preview-nav{width:270px;flex:none;height:100vh;position:sticky;top:0;overflow:auto;
  background:#f4f4f4;border-right:1px solid #ddd;padding:16px;box-sizing:border-box;font-size:14px}
#preview-nav ul{list-style:none;margin:0;padding-left:14px}#preview-nav>ul{padding:0}
#preview-nav a{color:#222;text-decoration:none;display:block;padding:2px 0}
#preview-nav a.on{font-weight:700;color:#e8461e}
#preview-nav .note{color:#888;font-size:12px;margin-top:16px}
#preview-main{flex:1;min-width:0;padding:24px 40px;max-width:1100px}
img{max-width:100%;height:auto}
.row{display:flex;gap:24px;flex-wrap:wrap}.col{flex:1;min-width:220px}
section{margin-bottom:24px}
table{border-collapse:collapse;margin:8px 0}td,th{border:1px solid #ccc;padding:4px 8px;text-align:left;vertical-align:top}
figure.embed{margin:16px 0}figure.embed iframe{width:100%;height:80vh;border:1px solid #ddd}
figcaption{font-size:13px;color:#666;margin-bottom:4px}
a.button{display:inline-block;background:#1a1a1a;color:#fff;padding:8px 16px;border-radius:4px;text-decoration:none}
</style>"""


def menu(items, current):
    out = ["<ul>"]
    for it in items:
        if it["type"] == "page":
            cls = ' class="on"' if it["path"] == current else ""
            out.append(f'<li><a{cls} href="{it["path"]}">{html.escape(it["title"])}</a>')
        else:
            out.append(f'<li><a href="{html.escape(it["url"])}">{html.escape(it["title"])} &#8599;</a>')
        if it.get("children"):
            out.append(menu(it["children"], current))
        out.append("</li>")
    out.append("</ul>")
    return "".join(out)


def hidden_links(current):
    rows = "".join(f'<a href="{h["path"]}"{" class=on" if h["path"] == current else ""}>{html.escape(h["path"])}</a>'
                   for h in SITE.get("hidden_pages", []))
    return f'<div class="note">Not in the menu:</div>{rows}'


class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *a, **kw):
        super().__init__(*a, directory=str(ROOT), **kw)

    def do_GET(self):
        path = unquote(urlparse(self.path).path)
        if path.startswith("/assets/"):
            return super().do_GET()
        clean = path.rstrip("/") or "/"
        page = ROOT / "content" / clean.strip("/") / "index.html" if clean != "/" else ROOT / "content" / "index.html"
        if not page.is_file():
            self.send_error(404, "Page not captured")
            return
        doc = page.read_text()
        nav = f'<nav id="preview-nav">{menu(SITE["navigation"], clean)}{hidden_links(clean)}</nav>'
        doc = doc.replace("</head>", STYLE + "</head>", 1)
        doc = doc.replace("<body>", f"<body>{nav}<div id=\"preview-main\">", 1)
        doc = doc.replace("</body>", f"<footer>{FOOTER}</footer></div></body>", 1)
        body = doc.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


if __name__ == "__main__":
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8000
    print(f"Serving on http://127.0.0.1:{port}/", flush=True)
    ThreadingHTTPServer(("127.0.0.1", port), Handler).serve_forever()
