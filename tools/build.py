#!/usr/bin/env python3
"""Build the Rodec documentation site from the captured content.

Input:   site.json, content/<path>/index.html, assets/, src/ (CSS, fonts, logo)
Output:  docs/  a static site with every page at its live path
         (docs/rodec-one/index.html -> /rodec-one), ready for GitHub Pages
         (branch, folder /docs) or any static host.

Usage:   python3 tools/build.py
Preview: python3 -m http.server 8000 --directory docs
"""
import html
import json
import re
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "docs"
SRC = ROOT / "src"
SITE = json.loads((ROOT / "site.json").read_text())
PAGES = {p["path"]: p for p in SITE["pages"]}
HOME_PATHS = ("/", "/documentation-home")

# Menu entries that are kept as pages (paths keep working) but not shown in
# the menu of the new site.
HIDE_FROM_MENU = {"/untitled-page", "/rodec-one/appendix-a-dimensions", "/rodec-one/appendix-b-performance"}

ARROW = '<span class="arr" aria-hidden="true">&rarr;</span>'
EXT = '<span class="ext" aria-hidden="true">&#8599;</span>'


def esc(s):
    return html.escape(s or "", quote=True)


# --------------------------------------------------------------------------- nav

def nav_items():
    return [it for it in SITE["navigation"] if it.get("path") not in HIDE_FROM_MENU]


def flat_pages():
    """All menu pages in reading order: (item, top-level item)."""
    out = []

    def walk(items, top):
        for it in items:
            if it["type"] == "page" and it.get("path") not in HIDE_FROM_MENU:
                out.append((it, top or it))
            walk(it.get("children", []), top or it)
    walk(nav_items(), None)
    return out


FLAT = flat_pages()
TOP_OF = {it["path"]: top for it, top in FLAT}
ITEM = {it["path"]: it for it, _ in FLAT}
PARENT = {}
for it, _ in FLAT:
    for c in it.get("children", []):
        if c.get("path"):
            PARENT[c["path"]] = it


def product_index(top):
    """01, 02 ... for the product groups (top-level pages after Home)."""
    tops = [it for it in nav_items() if it["type"] == "page" and it["path"] not in HOME_PATHS]
    return f"{tops.index(top) + 1:02d}" if top in tops else ""


def render_nav(current):
    trail = set()
    p = current
    while p in PARENT:
        trail.add(PARENT[p]["path"])
        p = PARENT[p]["path"]

    def link(it, cls=""):
        if it["type"] == "external":
            return f'<a class="ext-link{cls}" href="{esc(it["url"])}">{esc(it["title"])} {EXT}</a>'
        on = ' aria-current="page"' if it["path"] == current else ""
        return f'<a class="{cls.strip()}" href="{it["path"]}"{on}>{esc(it["title"])}</a>'

    def sub(items, depth):
        rows = []
        for it in items:
            if it.get("path") in HIDE_FROM_MENU:
                continue
            kids = it.get("children")
            if kids:
                open_ = " open" if (it.get("path") == current or it.get("path") in trail) else ""
                rows.append(f'<li><details{open_}><summary>{link(it)}</summary>'
                            f'<ul>{sub(kids, depth + 1)}</ul></details></li>')
            else:
                rows.append(f"<li>{link(it)}</li>")
        return "".join(rows)

    pages, external = [], []
    for it in nav_items():
        (external if it["type"] == "external" else pages).append(it)
    home = [it for it in pages if it["path"] in HOME_PATHS]
    products = [it for it in pages if it["path"] not in HOME_PATHS]
    groups = []
    for it in products:
        idx = product_index(it)
        kids = it.get("children")
        on = it["path"] == current or it["path"] in trail
        head = (f'<span class="idx">{idx}</span>'
                f'<a href="{it["path"]}"{" aria-current=page" if it["path"] == current else ""}>{esc(it["title"])}</a>')
        if kids:
            groups.append(f'<li class="grp"><details{" open" if on else ""}><summary>{head}</summary>'
                          f'<ul>{sub(kids, 1)}</ul></details></li>')
        else:
            groups.append(f'<li class="grp leaf">{head}</li>')
    homelink = "".join(f'<a class="nav-home" href="/documentation-home"'
                       f'{" aria-current=page" if current in HOME_PATHS else ""}>{esc(it["title"])}</a>' for it in home)
    ext = "".join(f"<li>{link(it)}</li>" for it in external)
    return (f'<nav class="side" aria-label="Documentation">{homelink}'
            f'<div class="side-label">Products</div><ul class="groups">{"".join(groups)}</ul>'
            f'<div class="side-label">Links</div><ul class="extlinks">{ext}</ul></nav>')


# --------------------------------------------------------------------------- content

def load_body(path):
    """Page body: a converted source in src/content/ wins over the capture."""
    rel = ("" if path == "/" else path.strip("/"))
    own = SRC / "content" / rel / "index.html"
    doc = (own if own.exists() else ROOT / "content" / rel / "index.html").read_text()
    body = doc.split("<main", 1)[1].split(">", 1)[1].rsplit("</main>", 1)[0]
    # assets: relative ../../assets/x -> /assets/x
    body = re.sub(r'(?:\.\./)+assets/', "/assets/", body)
    return body


def take_title(body, fallback):
    """Use the first h1 (if it opens the page) as page title; remove it from the body."""
    m = re.search(r"<h1[^>]*>(.*?)</h1>\s*", body, re.S)
    if m and m.start() < 400:
        title_html = re.sub(r"</?strong>", "", m.group(1)).strip()
        body = body[:m.start()] + body[m.end():]
        return title_html, body
    return esc(fallback), body


def tidy_body(body):
    # section background images (page banners) become a banner figure
    body = re.sub(r'<section data-background="([^"]+)">\s*',
                  r'<section class="has-banner"><figure class="banner"><img src="\1" alt="" loading="lazy"></figure>\n', body)
    # strong inside headings is redundant (headings are bold already)
    body = re.sub(r"(<h[1-6][^>]*>)<strong>(.*?)</strong>(</h[1-6]>)", r"\1\2\3", body)
    # empty sections
    body = re.sub(r"<section>\s*(<p></p>\s*|<br>\s*)*</section>\s*", "", body)
    # "Step N – Title" headings (h1/h2/h3 mixed on the old site): one level,
    # with the step number as a mono label
    body = re.sub(r'<h[1-6]( id="[^"]+")?>\s*Step (\d+)\s*(?:–|-|:)\s*(.*?)</h[1-6]>',
                  r'<h2 class="step"\1><span class="step-n">Step \2</span>\3</h2>', body, flags=re.S)
    # Google Sites button -> brand button with arrow
    body = re.sub(r'<a class="button" href="([^"]+)">(.*?)</a>',
                  lambda m: f'<a class="btn" href="{m.group(1)}">{m.group(2)}{ARROW}</a>', body)
    # lazy images
    body = body.replace("<img ", '<img loading="lazy" ')
    # tile columns: an image link + text become one card link target
    body = body.replace('<div class="col">\n<a href', '<div class="col tile">\n<a href')
    # rows whose columns each open with a photo: show the photos side by side
    # at one height (e.g. MX-F-101 and MX-F-102 faders)
    def gallery(m):
        cols = re.findall(r'<div class="col">\s*(.{0,5})', m.group(0))
        if len(cols) > 1 and all(c.startswith("<img") for c in cols):
            return m.group(0).replace('<div class="row">', '<div class="row gallery">', 1)
        return m.group(0)
    body = re.sub(r'<div class="row">.*?\n</div>\n</div>', gallery, body, flags=re.S)
    # tables: wrap for horizontal scroll on phones
    body = re.sub(r"(<table>.*?</table>)", r'<div class="table-wrap">\1</div>', body, flags=re.S)
    # Google Doc embed: show our own PDF copy instead of Google's preview
    body = re.sub(r'(<figure class="embed" data-embed-type="google-document"[^>]*data-file="([^"]+)"[^>]*>)<iframe src="[^"]+"',
                  r'\1<iframe src="\2#view=FitH" title="PDF"', body)
    # Google Doc embed: preview + download button
    body = re.sub(r'<figcaption><a href="(/assets/files/[^"]+\.pdf)">(.*?)</a></figcaption>',
                  r'<figcaption><span>\2</span><a class="btn" href="\1" download>Download PDF' + ARROW + "</a></figcaption>",
                  body)
    return body


def toc(body):
    items = re.findall(r'<h([23])[^>]*?\bid="([^"]+)"[^>]*>(.*?)</h\1>', body, re.S)
    rows = []
    for lvl, hid, text in items:
        t = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", text)).strip()
        if t:
            rows.append(f'<li class="l{lvl}"><a href="#{esc(hid)}">{t}</a></li>')
    if len(rows) < 3:
        return ""
    return f'<aside class="toc"><div class="side-label">On this page</div><ul>{"".join(rows)}</ul></aside>'



# Line icons for cards without a picture, picked by keywords in the card title.
# 64 x 64, ink lines with one orange accent, like the rest of the house style.
_I = 'viewBox="0 0 64 64" fill="none" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"'
CARD_ICONS = [
    (("safety",), f'''<svg {_I}><path d="M32 9 L57 53 H7 Z" stroke="#111214"/>
<path d="M32 25 V39" stroke="#FF5C00" stroke-width="3"/><circle cx="32" cy="46" r="1.8" fill="#FF5C00" stroke="none"/></svg>'''),
    (("troubleshoot",), f'''<svg {_I}><circle cx="27" cy="27" r="16" stroke="#111214"/><path d="M39 39 L54 54" stroke="#111214" stroke-width="4"/>
<path d="M16 28 H20 L23 21 L27 34 L31 24 L33 28 H38" stroke="#FF5C00"/></svg>'''),
    (("dimension",), f'''<svg {_I}><rect x="12" y="20" width="40" height="26" rx="2" stroke="#111214"/>
<path d="M17 27 H47 M17 33 H35" stroke="#111214" stroke-width="1.5" opacity=".45"/>
<path d="M12 54 H52 M12 51 V57 M52 51 V57" stroke="#FF5C00"/><path d="M58 20 V46 M55 20 H61 M55 46 H61" stroke="#FF5C00"/></svg>'''),
    (("performance", "specification"), f'''<svg {_I}><path d="M10 10 V54 H56" stroke="#111214"/>
<path d="M10 22 H56 M10 34 H56 M10 46 H56" stroke="#111214" stroke-width="1" opacity=".25"/>
<path d="M12 44 C16 30 20 28 26 28 H44 C49 28 52 31 55 40" stroke="#FF5C00" stroke-width="2.5"/></svg>'''),
]


def card_icon(title):
    t = title.lower()
    for keys, svg in CARD_ICONS:
        if any(k in t for k in keys):
            return svg
    return None


def children_grid(path, thumbs=None, texts=None):
    """Cards for the subpages; with thumbnails (href -> image url) the cards
    get a picture, with texts (href -> line) a short description."""
    it = ITEM.get(path)
    kids = [k for k in (it or {}).get("children", []) if k["type"] == "page"
            and k["path"] not in HIDE_FROM_MENU]
    if not kids:
        return ""
    thumbs, texts = thumbs or {}, texts or {}
    rich = bool(thumbs)
    cards = []
    for i, k in enumerate(kids, 1):
        img = thumbs.get(k["path"])
        icon = card_icon(k["title"]) if rich and not img else None
        pic = (f'<span class="card-img"><img src="{img}" alt="" loading="lazy"></span>' if img
               else f'<span class="card-img icon">{icon}</span>' if icon
               else '<span class="card-img empty"></span>') if rich else ""
        txt = f'<span class="d">{texts[k["path"]]}</span>' if texts.get(k["path"]) else ""
        cards.append(f'<a class="card{" rich" if rich else ""}" href="{k["path"]}">{pic}<span class="idx">{i:02d}</span>'
                     f'<span class="t">{esc(k["title"])}{txt}</span>{ARROW}</a>')
    return (f'<section class="children{" rich" if rich else ""}"><div class="rdc-label"><span class="rule"></span>In this section</div>'
            f'<div class="cards">{"".join(cards)}</div></section>')


def tiles_to_cards(body, path):
    """Rows of image tiles that only link to this page's subpages duplicate
    the "In this section" cards: take them out and keep their images as card
    thumbnails. Returns (body, {href: img})."""
    kids = {k["path"] for k in (ITEM.get(path) or {}).get("children", []) if k.get("path")}
    thumbs = {}

    def repl(m):
        block = m.group(0)
        links = re.findall(r'<div class="col tile">\s*<a href="([^"]+)"><img [^>]*src="([^"]+)"', block)
        ncols = block.count('<div class="col')
        if links and len(links) == ncols and all(h in kids for h, _ in links):
            for h, src in links:
                thumbs.setdefault(h, src)
            return ""
        return block
    body = re.sub(r'<div class="row">.*?\n</div>\n</div>\n', repl, body, flags=re.S)
    return body, thumbs


def pager(path):
    order = [it["path"] for it, _ in FLAT if it["path"] not in HOME_PATHS]
    if path not in order:
        return ""
    i = order.index(path)
    out = []
    if i > 0:
        p = ITEM[order[i - 1]]
        out.append(f'<a class="prev" href="{p["path"]}"><span class="k">&larr; Previous</span>{esc(p["title"])}</a>')
    else:
        out.append("<span></span>")
    if i < len(order) - 1:
        n = ITEM[order[i + 1]]
        out.append(f'<a class="next" href="{n["path"]}"><span class="k">Next &rarr;</span>{esc(n["title"])}</a>')
    return f'<nav class="pager" aria-label="Previous and next page">{"".join(out)}</nav>'


def crumbs(path):
    chain = []
    p = path
    while p in PARENT:
        p = PARENT[p]["path"]
        chain.insert(0, ITEM[p])
    if not chain:
        return ""
    links = "".join(f'<a href="{c["path"]}">{esc(c["title"])}</a><span class="sep">/</span>' for c in chain)
    return f'<div class="crumbs">{links}</div>'


# --------------------------------------------------------------------------- layout

def layout(path, title, main, current_nav, description="", head="", scripts=""):
    canonical = f"https://documentation.rodec.com{path}"
    nav = render_nav(current_nav)
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{esc(title)} | Rodec Documentation</title>
<meta name="description" content="{esc(description or title + ' - Rodec documentation')}">
<link rel="canonical" href="{canonical}">
<link rel="icon" href="/assets/brand/favicon.svg" type="image/svg+xml">
<link rel="preload" href="/assets/fonts/ibm-plex-sans-latin-400-normal.woff2" as="font" type="font/woff2" crossorigin>
<link rel="stylesheet" href="/assets/css/rodec-docs.css">
{head}
</head>
<body>
<a class="skip" href="#content">Skip to content</a>
<header class="top">
  <div class="top-in">
    <button class="menu-btn" aria-label="Menu" aria-expanded="false" aria-controls="sidebar"><span></span><span></span></button>
    <a class="brand" href="/documentation-home"><img src="/assets/brand/rodec-logo.webp" alt="RODEC" width="95" height="22"><span>Documentation</span></a>
    <nav class="top-links" aria-label="Rodec">
      <a href="https://www.rodec.com/configurator">Configurator {EXT}</a>
      <a href="https://www.rodec.com/">rodec.com {EXT}</a>
      <a class="btn small" href="mailto:info@rodec.com">Contact</a>
    </nav>
  </div>
</header>
<div class="shell">
  <div class="sidebar" id="sidebar">{nav}</div>
  <main id="content">
{main}
  </main>
</div>
<footer class="foot">
  <div class="foot-in">
    <div>
      <div class="rdc-label light"><span class="rule"></span>Rodec</div>
      <p class="foot-title">Analog love <em>from Belgium.</em></p>
    </div>
    <div class="foot-links">
      <a href="https://www.rodec.com">www.rodec.com</a>
      <a href="mailto:info@rodec.com">info@rodec.com</a>
      <a href="https://www.rodec.com/configurator">Configurator</a>
    </div>
  </div>
  <div class="foot-base"><span>&copy; RODEC &middot; TDR Media BV</span><span>Documentation</span></div>
</footer>
<script>
(function(){{var b=document.querySelector('.menu-btn');if(!b)return;
b.addEventListener('click',function(){{var o=document.body.classList.toggle('nav-open');b.setAttribute('aria-expanded',o)}});}})();
</script>
{scripts}
</body>
</html>
"""



# ---------------------------------------------------------------------------
# Custom HTML embeds that become part of the page instead of an iframe.

def render_presets(code):
    """SideStepper preset bank: the embed is static HTML (cards with step
    blocks); keep its data, render it in the site style."""
    from bs4 import BeautifulSoup
    soup = BeautifulSoup(code, "lxml")
    sub = soup.select_one(".subtitle")
    cards = []
    for c in soup.select(".card"):
        name = c.select_one("h2").get_text(strip=True)
        badge = c.select_one(".badge")
        kind = badge.get_text(strip=True) if badge else ""
        desc = c.select_one(".desc").get_text(" ", strip=True) if c.select_one(".desc") else ""
        meta = c.select_one(".meta").get_text(" ", strip=True) if c.select_one(".meta") else ""
        steps = []
        for cell in c.select(".step-cell"):
            m = re.search(r"state: (\w+), length: (\d+), nudge: (\d+)", cell.get("title", ""))
            if not m:
                continue
            state, length, nudge = m.group(1), int(m.group(2)), int(m.group(3))
            state = "rest" if state == "empty" else state
            label = f"{state}, length {length}" + (", nudged" if nudge else "")
            steps.append(f'<span class="st {state}{" nudge" if nudge else ""}" style="flex-grow:{length}" title="{label}"></span>')
        cards.append(f'''<article class="pr-card">
  <header><h3>{esc(name)}</h3>{f'<span class="pr-kind {kind.lower()}">{esc(kind)}</span>' if kind else ''}</header>
  <p>{esc(desc)}</p>
  <div class="pr-steps" role="img" aria-label="{len(steps)} steps">{''.join(steps)}</div>
  <div class="pr-meta">{esc(meta)}</div>
</article>''')
    intro = f'<p class="pr-intro">{esc(sub.get_text(" ", strip=True))}</p>' if sub else ""
    legend = ('<div class="pr-legend"><span><i class="st left"></i>Left</span><span><i class="st center"></i>Center</span>'
              '<span><i class="st right"></i>Right</span><span><i class="st rest"></i>Rest</span>'
              '<span><i class="st center nudge"></i>Nudged</span><span class="note">Block width = gate length</span></div>')
    return f'<div class="presets">{intro}{legend}<div class="pr-grid">{"".join(cards)}</div></div>'


def render_bank_manager(code):
    """SideStepper Bank Manager: a small Web Serial app. Its markup and script
    go into the page as they are (all wiring is by element id); its own dark
    stylesheet is replaced by bank-manager.css in the site style."""
    body = code[code.index("<body"):]
    body = body[body.index(">") + 1:]
    markup, script = body.split("<script>", 1)
    script = script.rsplit("</script>", 1)[0]
    markup = re.sub(r'<img [^>]*class="logo-img"[^>]*>', "", markup)
    markup = markup.replace('<span class="header-title">Bank Manager</span>',
                            '<span class="header-title">SideStepper Bank Manager</span>')
    return (f'<div class="bm">{markup}</div>\n'
            f'<script>\n(function () {{\n{script}\n}})();\n</script>')


EMBED_RENDERERS = {
    "rodec-m-110-sidestepper--presets-embed-01.html": render_presets,
    "rodec-m-110-sidestepper--bank-manager-embed-01.html": render_bank_manager,
}


def inline_embeds(body):
    """Replace iframe embeds that have a renderer by the rendered HTML.
    Returns (body, [stylesheets the page needs])."""
    css = []

    def repl(m):
        name = m.group(1)
        fn = EMBED_RENDERERS.get(name)
        if not fn:
            return m.group(0)
        css.append("bank-manager" if "bank-manager" in name else "presets")
        return fn((ROOT / "assets" / "embeds" / name).read_text())
    body = re.sub(r'<figure class="embed" data-embed-type="custom-html" data-embed-source="[^"]*/assets/embeds/([^"]+)">.*?</figure>',
                  repl, body, flags=re.S)
    return body, css


def product_intro(body):
    """A page that opens with a lone product photo and then text gets an intro
    block: the photo in a card, the first paragraph beside it."""
    m = re.match(r'\s*<section>\s*(<img [^>]+>)\s*</section>\s*<section>\s*(<p>.*?</p>)', body, re.S)
    if not m:
        return body
    img, lead = m.group(1), m.group(2)
    rest = body[m.end():]
    return (f'<div class="intro"><figure class="intro-img">{img}</figure>'
            f'<div class="intro-lead">{lead}</div></div>\n<section>' + rest)


def build_page(path):
    page = PAGES[path]
    body = load_body(path)
    item = ITEM.get(path)
    fallback = (item or {}).get("title") or page.get("title") or ""
    title_html, body = take_title(body, fallback)
    plain_title = re.sub(r"<[^>]+>", "", title_html).strip().lower()
    body = re.sub(r'^(\s*<section>\s*</section>\s*)+', "", body)
    body = re.sub(r'^(\s*<section>\s*)<h[1-6][^>]*>(?:<strong>)?([^<]*)(?:</strong>)?</h[1-6]>\s*',
                  lambda m: m.group(1) if m.group(2).strip().lower() == plain_title else m.group(0), body)
    body = tidy_body(body)
    body = swap_sharp_images(body)
    body, extra_css = inline_embeds(body)
    body, thumbs = tiles_to_cards(body, path)
    body = product_intro(body)
    top = TOP_OF.get(path)
    idx = product_index(top) if top else ""
    label_text = esc(top["title"]) if top else "Documentation"
    if top is None and path not in HOME_PATHS:
        label_text = "Rodec"
    label = (f'<div class="rdc-label">{f"<span class=idx>{idx}</span>" if idx else ""}'
             f'<span class="rule"></span>{label_text}</div>')
    empty = not re.sub(r"<[^>]+>|\s|&nbsp;", "", body) and "<img" not in body and "<iframe" not in body
    kids = children_grid(path, thumbs)
    if empty and not kids:
        body = '<p class="empty">This page has no content yet.</p>'
    main = f"""<div class="page">
<article class="doc">
<header class="doc-head">
{label}
{crumbs(path)}
<h1 class="rdc-title">{title_html}</h1>
</header>
<div class="prose">
{body}
</div>
{kids}
{pager(path)}
</article>
{toc(body)}
</div>"""
    plain = re.sub(r"<[^>]+>", "", title_html)
    head = "".join(f'<link rel="stylesheet" href="/assets/pages/{c}.css">' for c in extra_css)
    return layout(path, html.unescape(plain), main, path, head=head)


def build_home(path):
    body = swap_sharp_images(load_body("/documentation-home"))
    # product tiles: <div class="col"><h2>Name</h2><a href><img></a>[<p><a>Subtitle</a></p>]</div>
    tiles = re.findall(r'<div class="col">\s*<h2[^>]*>(.*?)</h2>\s*<a href="([^"]+)"><img src="([^"]+)"[^>]*></a>'
                       r'(?:<p><a [^>]*>(.*?)</a></p>)?\s*</div>', body, re.S)
    cards = []
    for i, (name, href, img, sub) in enumerate(tiles, 1):
        top = ITEM.get(href)
        cards.append(
            f'<a class="prod" href="{href}"><span class="img"><img src="{img}" alt="" loading="lazy"></span>'
            f'<span class="meta"><span class="name">{name}</span>'
            f'<span class="sub">{sub or ""}</span></span>'
            f'<span class="go">Read the manual{ARROW}</span></a>')
    disclaimer = ""
    m = re.search(r'(<h2[^>]*>Disclaimer</h2>.*?)</section>', body, re.S)
    if m:
        disclaimer = re.sub(r"<br>", "", m.group(1))
    main = f"""<section class="hero" style="--hero:url(/assets/renders/mx-modular-side-config.webp)">
  <div class="rdc-label light"><span class="idx">00</span><span class="rule"></span>Documentation</div>
  <h1 class="rdc-title">Manuals &amp; specs. <em>For every Rodec.</em></h1>
  <p class="rdc-copy">User guides, connections, data and dimensions for the MX Modular console, the Rodec ONE and every 100 series module.</p>
  <div class="rdc-actions"><a class="btn" href="/rodec-mx-modular">MX Modular manual{ARROW}</a><a class="btn ghost" href="/rodec-one">Rodec ONE</a></div>
</section>
<section class="products">
  <div class="rdc-head"><div><div class="rdc-label"><span class="idx">01</span><span class="rule"></span>Products</div>
  <h2 class="rdc-title small">Choose <em>your product.</em></h2></div></div>
  <div class="prod-grid">{"".join(cards)}</div>
</section>
<section class="disclaimer prose">{disclaimer}</section>"""
    return layout(path, "Documentation Home", f'<div class="home">{main}</div>', "/documentation-home",
                  "Manuals, specifications and guides for Rodec mixing consoles and 100 series modules.")


# Hand-made pages that replace the captured content at their live path:
# live path -> (source name in src/pages, title)
CUSTOM = {
    "/rodec-mx-f-101-102-channel-control": ("channel-control", "MX-F-101 / 102 Channel control"),
    "/rodec-mx-modular/backpanel-connections": ("backpanel", "Backpanel connections"),
}


def prepare_backpanel():
    """The backpanel render, cropped to the console (it has a transparent
    background and an empty band below). Returns size and crop offset."""
    from PIL import Image
    src = ROOT / "assets" / "images" / "rodec-mx-modular--backpanel-connections-01.png"
    out = OUT / "assets" / "pages" / "backpanel"
    out.mkdir(parents=True, exist_ok=True)
    im = Image.open(src).convert("RGBA")
    box = im.getchannel("A").point(lambda a: 255 if a > 8 else 0).getbbox()
    crop = im.crop(box)
    crop.save(out / "mx-modular-backpanel.webp", "WEBP", quality=90, method=6)
    return {"src": "/assets/pages/backpanel/mx-modular-backpanel.webp",
            "w": crop.width, "h": crop.height, "ox": box[0], "oy": box[1]}


def prepare_channel_control():
    """Web versions of the MX-F-101/102 render layers (src/img/channel-control,
    rendered from the 3D model of the console): every overlay
    is cropped to its visible part. Returns the panel data for the page."""
    from PIL import Image  # only needed for this page
    src = SRC / "img" / "channel-control"
    out = OUT / "assets" / "pages" / "channel-control"
    out.mkdir(parents=True, exist_ok=True)
    panels = {}
    for m in ("101", "102"):
        meta = json.loads((src / f"mx-f-{m}.json").read_text())
        layers = {}
        for name in ("base", "fader-cap", "knob-pan", "knob-aux1", "knob-aux2", "leds-on",
                     "buttons-lit", "on-down", "solo-down", "switch-x", "switch-y",
                     "on-lit", "solo-lit", "on-down-lit", "solo-down-lit"):
            f = src / f"mx-f-{m}-{name}.webp"
            if not f.exists():  # the key-light layers are optional
                continue
            im = Image.open(f).convert("RGBA")
            if name == "base":
                box = (0, 0, im.width, im.height)
            elif name.startswith(("on-", "solo-")):
                key = "ON" if name.startswith("on-") else "SOLO"
                box = tuple(meta["keycaps"][key]["patch"])
            elif name.startswith("switch-"):
                box = tuple(meta["xfader_switch"]["patch"])
            else:
                box = im.getchannel("A").getbbox()
            crop = im.crop(box)
            fn = f"mx-f-{m}-{name}.webp"
            crop.save(out / fn, "WEBP", quality=90, method=6)
            layers[name] = {"src": f"/assets/pages/channel-control/{fn}", "box": list(box)}
        meta["layers_web"] = layers
        panels[m] = meta
    shutil.copy(src / "mx-f-102-hero.webp", out / "mx-f-102-hero.webp")
    return panels


def build_custom(path, name, title):
    body = (SRC / "pages" / f"{name}.html").read_text()
    if name == "channel-control":
        data = json.dumps(prepare_channel_control(), separators=(",", ":"))
        body += f'<script type="application/json" id="panels">{data}</script>'
    if name == "backpanel":
        body += f'<script type="application/json" id="bp-data">{json.dumps(prepare_backpanel())}</script>'
    main = body + f'<div class="page" style="padding-top:0">{pager(path)}</div>'
    head = f'<link rel="stylesheet" href="/assets/pages/{name}.css">'
    scripts = f'<script src="/assets/pages/{name}.js" defer></script>'
    return layout(path, title, main, path, head=head, scripts=scripts)


# ---------------------------------------------------------------------------
# Annotated pages: a panel image with numbered badges and a legend, then the
# full original text. One JSON file per page in src/annotations/ (see the
# README there). Coordinates are in pixels of the original image.

ANNOTATIONS = {}
for _f in sorted((SRC / "annotations").glob("*.json")) if (SRC / "annotations").exists() else []:
    _cfg = json.loads(_f.read_text())
    _cfg["_file"] = _f.name
    ANNOTATIONS[_cfg["path"]] = _cfg


def _slug(t):
    return re.sub(r"[^a-z0-9]+", "-", t.lower()).strip("-")


def add_ref_anchor(body, ref, file):
    """Give the element that a legend item points to an id; return (body, id)."""
    if "id" in ref:
        if f'id="{ref["id"]}"' not in body:
            raise SystemExit(f"{file}: id {ref['id']} not found")
        return body, ref["id"]
    text = ref["strong"]
    rid = "ref-" + _slug(text)
    if f'id="{rid}"' in body:
        return body, rid
    pat = re.compile(r"<(p|li|h[1-6])((?: [^>]*)?)>(\s*)<strong>" + re.escape(html.escape(text, quote=False)))
    m = pat.search(body)
    if not m:
        raise SystemExit(f"{file}: no <strong>{text}</strong> to link to")
    attrs = m.group(2)
    if " id=" in attrs:
        return body, re.search(r'id="([^"]+)"', attrs).group(1)
    body = body[:m.start()] + f'<{m.group(1)}{attrs} id="{rid}">{m.group(3)}<strong>' + body[m.start() + len(m.group(0)) - len(html.escape(text, quote=False)):]
    return body, rid


SHARP = SRC / "img" / "panels-sharp"


def sharp_version(src_rel):
    """A sharper re-render of an image in assets/images, if one was made
    (src/img/panels-sharp/<same name>.webp, same framing). Returns
    (path relative to ROOT, scale x, scale y) or None."""
    from PIL import Image
    cand = SHARP / (Path(src_rel).stem + ".webp")
    if not cand.exists() or not (ROOT / src_rel).exists():
        return None
    w0, h0 = Image.open(ROOT / src_rel).size
    w1, h1 = Image.open(cand).size
    return str(cand.relative_to(ROOT)), w1 / w0, h1 / h0


def swap_sharp_images(body):
    """Point plain <img> tags at the sharp re-renders where they exist."""
    def repl(m):
        name = m.group(1)
        sv = sharp_version(f"assets/images/{name}")
        if not sv:
            return m.group(0)
        out = OUT / "assets" / "images-sharp"
        out.mkdir(parents=True, exist_ok=True)
        shutil.copy(ROOT / sv[0], out / Path(sv[0]).name)
        return f'src="/assets/images-sharp/{Path(sv[0]).name}"'
    return re.sub(r'src="/assets/images/([^"]+)"', repl, body)


def hero_asset(src_rel, name, max_w=1920):
    """Copy a large picture (render, product photo) as WebP into the site."""
    from PIL import Image
    out = OUT / "assets" / "pages" / "heroes"
    out.mkdir(parents=True, exist_ok=True)
    target = out / f"{name}.webp"
    if not target.exists():
        im = Image.open(ROOT / src_rel)
        im = im.convert("RGBA") if im.mode in ("RGBA", "LA", "P") else im.convert("RGB")
        if im.width > max_w:
            im = im.resize((max_w, round(im.height * max_w / im.width)), Image.LANCZOS)
        im.save(target, "WEBP", quality=86, method=6)
    return f"/assets/pages/heroes/{name}.webp"


def prepare_panel_image(src_rel, name, crop=None):
    """Copy a panel image as WebP; cut-out renders (alpha) are cropped to the
    object. Returns (url, width, height, ox, oy, has_alpha)."""
    from PIL import Image
    im = Image.open(ROOT / src_rel)
    has_alpha = im.mode in ("RGBA", "LA") or "transparency" in im.info
    im = im.convert("RGBA") if has_alpha else im.convert("RGB")
    ox = oy = 0
    if crop:
        ox, oy = crop[0], crop[1]
        im = im.crop(tuple(crop))
    elif has_alpha:
        box = im.getchannel("A").point(lambda a: 255 if a > 8 else 0).getbbox()
        if box:
            ox, oy = box[0], box[1]
            im = im.crop(box)
    out = OUT / "assets" / "pages" / "annotated"
    out.mkdir(parents=True, exist_ok=True)
    im.save(out / f"{name}.webp", "WEBP", quality=90, method=6)
    return f"/assets/pages/annotated/{name}.webp", im.width, im.height, ox, oy, has_alpha


def build_annotated(path, cfg):
    file = cfg["_file"]
    body = load_body(path)
    fallback = (ITEM.get(path) or {}).get("title") or PAGES[path].get("title") or ""
    _, body = take_title(body, fallback)
    # text corrections against the captured page: [["find", "replace"], ...]
    for find, repl in cfg.get("corrections", []):
        if find not in body:
            raise SystemExit(f"{file}: correction text not found: {find}")
        body = body.replace(find, repl)
    for img in cfg.get("remove_images", []):
        body = re.sub(r'<img src="/?(?:\.\./)*assets/images/' + re.escape(img) + r'"[^>]*>', "", body)
        body = re.sub(r' data-background="[^"]*' + re.escape(img) + '"', "", body)
    body = re.sub(r'<div class="col">\s*</div>\n?', "", body)
    panels_html, n = [], 0
    for pi, panel in enumerate(cfg.get("panels", [])):
        # the panel image is shown in the panel, so take it out of the text
        img_name = Path(panel["image"]).name
        body = re.sub(r'<img src="/assets/images/' + re.escape(img_name) + r'"[^>]*>', "", body)
        sv = sharp_version(panel["image"])
        sx = sy = 1
        if sv:   # same framing, more pixels: scale every coordinate
            src_img, sx, sy = sv
            for it in panel["items"]:
                it["at"] = [it["at"][0] * sx, it["at"][1] * sy]
                if it.get("rect"):
                    r = it["rect"]
                    it["rect"] = [r[0] * sx, r[1] * sy, r[2] * sx, r[3] * sy]
        crop = panel.get("crop")
        if crop and sv:
            crop = [round(crop[0] * sx), round(crop[1] * sy), round(crop[2] * sx), round(crop[3] * sy)]
        url, W, H, ox, oy, alpha = prepare_panel_image(sv[0] if sv else panel["image"], f"{_slug(path)}-{pi + 1}", crop)
        pct = lambda v, size, o: f"{(v - o) / size * 100:.3f}%"
        badges, zones, legend = [], [], []
        for it in panel["items"]:
            n += 1
            ref_link = ""
            if it.get("link"):
                ref_link = f'<a class="an-more an-go" href="{it["link"]}">Open page</a>'
            if it.get("ref"):
                body, rid = add_ref_anchor(body, it["ref"], file)
                ref_link = f'<a class="an-more" href="#{rid}">Read more</a>'
            x, y = it["at"]
            badges.append(f'<button class="an-badge" data-n="{n}" style="left:{pct(x, W, ox)};top:{pct(y, H, oy)}" '
                          f'aria-label="{n}: {esc(it["name"])}">{n}</button>')
            if it.get("rect"):
                r = it["rect"]
                zones.append(f'<span class="an-zone" data-n="{n}" style="left:{pct(r[0], W, ox)};top:{pct(r[1], H, oy)};'
                             f'width:{(r[2] - r[0]) / W * 100:.3f}%;height:{(r[3] - r[1]) / H * 100:.3f}%"></span>')
            label = f'<span class="an-key">{esc(it["label"])}</span>' if it.get("label") else ""
            legend.append(f'<li data-n="{n}"><button class="an-item"><span class="an-n">{n:02d}</span>'
                          f'<span class="an-name">{esc(it["name"])}{label}</span>'
                          f'<span class="an-text">{it["text"]}</span></button>{ref_link}</li>')
        shape = "wide" if W > H * 1.6 else "tall"
        style = f"--nat-w:{W}px;--nat-h:{H}px;--ar:{H / W:.4f}"
        cap = f'<figcaption>{esc(panel["caption"])}</figcaption>' if panel.get("caption") else ""
        head = ""
        if panel.get("heading"):
            head = f'<h2 class="an-panel-title">{esc(panel["heading"])}</h2>'
        panels_html.append(f"""<section class="an-panel {shape}{' cutout' if alpha else ''}{' dark' if panel.get('dark') else ''}">
{head}<div class="an-grid">
  <figure class="an-figure"><div class="an-canvas" style="{style}">
    <img src="{url}" alt="{esc(panel.get('alt') or fallback)}" width="{W}" height="{H}" draggable="false">
    <div class="an-layer">{''.join(zones)}{''.join(badges)}</div>
  </div>{cap}</figure>
  <ol class="an-legend">{''.join(legend)}</ol>
</div></section>""")
    body = tidy_body(body)
    body = re.sub(r"<section>\s*</section>\s*", "", body)
    body = swap_sharp_images(body)
    body, thumbs = tiles_to_cards(body, path)
    for href, src in cfg.get("card_images", {}).items():
        thumbs[href] = hero_asset(src, "card-" + _slug(href)) if src.startswith("src/") else src
    has_text = bool(re.sub(r"<[^>]+>|\s|&nbsp;", "", body))
    blocks = swap_sharp_images("".join((SRC / "pages" / "fragments" / f).read_text() for f in cfg.get("blocks", [])))
    blocks_before = "".join((SRC / "pages" / "fragments" / f).read_text() for f in cfg.get("blocks_before", []))
    hero_img = ""
    if cfg.get("hero_image"):
        url = hero_asset(cfg["hero_image"], "hero-" + _slug(path))
        hero_img = f' style="--hero:url({url})"'
    top = TOP_OF.get(path)
    idx = product_index(top) if top else ""
    title, em = cfg.get("title") or fallback, cfg.get("title_em")
    h1 = f'{esc(title)}{" <em>" + esc(em) + "</em>" if em else ""}'
    lead = f'<p class="rdc-copy">{cfg["lead"]}</p>' if cfg.get("lead") else ""
    if cfg.get("specs"):
        lead += '<div class="rdc-specs">' + "".join(
            f"<div><span>{esc(k)}</span>{v}</div>" for k, v in cfg["specs"]) + "</div>"
    main = f"""<div class="an">
<section class="an-hero{' visual ' + cfg.get('hero_style', 'dark') if hero_img else ''}"{hero_img}>
  <div class="rdc-label">{f"<span class=idx>{idx}</span>" if idx else ""}<span class="rule"></span>{esc(top["title"]) if top else "Rodec"}</div>
  {crumbs(path)}
  <h1 class="rdc-title">{h1}</h1>
  {lead}
</section>
{blocks_before}
{''.join(panels_html)}
{blocks}
<div class="page an-text">
<article class="doc">{f'<div class="prose">{body}</div>' if has_text else ''}{children_grid(path, thumbs, cfg.get("card_texts"))}{pager(path)}</article>
{toc(body) if has_text else ''}
</div>
</div>"""
    head = '<link rel="stylesheet" href="/assets/pages/annotated.css">'
    scripts = '<script src="/assets/pages/annotated.js" defer></script>'
    return layout(path, title.rstrip(". "), main, path, head=head, scripts=scripts)


def build_404():
    main = f"""<div class="page"><article class="doc"><header class="doc-head">
<div class="rdc-label"><span class="idx">404</span><span class="rule"></span>Not found</div>
<h1 class="rdc-title">Page not <em>found.</em></h1></header>
<div class="prose"><p>This page does not exist (anymore). Pick a product in the menu, or go to the
<a href="/documentation-home">documentation home</a>.</p></div></article></div>"""
    return layout("/404", "Page not found", main, "")


def main():
    if OUT.exists():
        shutil.rmtree(OUT)
    OUT.mkdir()
    # static files
    shutil.copytree(ROOT / "assets" / "images", OUT / "assets" / "images")
    shutil.copytree(ROOT / "assets" / "files", OUT / "assets" / "files")
    shutil.copytree(ROOT / "assets" / "embeds", OUT / "assets" / "embeds")
    shutil.copytree(SRC / "fonts", OUT / "assets" / "fonts")
    (OUT / "assets" / "css").mkdir(parents=True)
    shutil.copy(SRC / "rodec-docs.css", OUT / "assets" / "css" / "rodec-docs.css")
    shutil.copytree(SRC / "img", OUT / "assets" / "brand",
                    ignore=shutil.ignore_patterns("channel-control", "renders", "panels-sharp", "100-series", "breakout"))
    (OUT / "assets" / "pages").mkdir(parents=True)
    for f in (SRC / "pages").glob("*.*"):
        if f.suffix in (".css", ".js"):
            shutil.copy(f, OUT / "assets" / "pages" / f.name)
    shutil.copytree(SRC / "img" / "renders", OUT / "assets" / "renders")
    for d in ("100-series", "breakout"):   # images of documents converted by tools/convert_gdoc.py
        if (SRC / "img" / d).exists():
            shutil.copytree(SRC / "img" / d, OUT / "assets" / d)
    (OUT / ".nojekyll").write_text("")

    n = 0
    for path in PAGES:
        if path in HOME_PATHS:
            html_out = build_home(path)
        elif path in CUSTOM:
            html_out = build_custom(path, *CUSTOM[path])
        elif path in ANNOTATIONS:
            html_out = build_annotated(path, ANNOTATIONS[path])
        else:
            html_out = build_page(path)
        d = OUT if path == "/" else OUT / path.strip("/")
        d.mkdir(parents=True, exist_ok=True)
        (d / "index.html").write_text(html_out)
        n += 1
    (OUT / "404.html").write_text(build_404())
    print(f"built {n} pages into {OUT.relative_to(ROOT)}/")


if __name__ == "__main__":
    main()
