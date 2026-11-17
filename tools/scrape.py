#!/usr/bin/env python3
"""Scrape the public Google Sites documentation at https://documentation.rodec.com.

Read-only: it only issues GET requests to the live site and to public Google
endpoints (images, Drive / Docs / Sheets exports).

Outputs (relative to the repo root):
  raw/<path>/index.html      original HTML of every page, untouched
  content/<path>/index.html  clean semantic HTML of the page body
  content/_footer.html       the site-wide footer (clean)
  assets/images/             every image (largest size available)
  assets/files/              public Drive / Docs files (PDF) and Sheets (CSV)
  assets/embeds/             original code of every custom HTML embed
  assets/manifest.json       sha256 -> file name, keeps names stable on rerun
  site.json                  navigation tree, hidden pages, per page assets,
                             links and embeds

Usage:  python3 tools/scrape.py            (from the repo root, inside the venv)
"""
import hashlib
import html
import io
import csv
import json
import mimetypes
import re
import sys
import time
from collections import OrderedDict
from pathlib import Path
from urllib.parse import urlparse, parse_qs, unquote, urljoin

import requests
from bs4 import BeautifulSoup, NavigableString, Comment, Tag

BASE = "https://documentation.rodec.com"
HOST = "documentation.rodec.com"
ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "raw"
CONTENT = ROOT / "content"
ASSETS = ROOT / "assets"
IMAGES = ASSETS / "images"
FILES = ASSETS / "files"
EMBEDS = ASSETS / "embeds"
MANIFEST = ASSETS / "manifest.json"

# Pages that are reachable but not linked from the menu. The crawler also finds
# any other page linked from content.
EXTRA_SEEDS = ["/rodec-100-series-configurator"]

S = requests.Session()
S.headers["User-Agent"] = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0 Safari/537.36"
)

INLINE_KEEP = {"a", "strong", "b", "em", "i", "u", "sup", "sub", "code", "br", "small", "s"}
BLOCK_KEEP = {"h1", "h2", "h3", "h4", "h5", "h6", "p", "ul", "ol", "li", "blockquote",
              "table", "thead", "tbody", "tfoot", "tr", "th", "td", "caption", "hr", "pre"}
DROP = {"script", "style", "svg", "noscript", "link", "meta", "button", "input"}


def log(*a):
    print(*a, file=sys.stderr, flush=True)


def get(url, **kw):
    for attempt in range(4):
        try:
            r = S.get(url, timeout=60, **kw)
            if r.status_code in (429, 500, 502, 503) and attempt < 3:
                time.sleep(2 * (attempt + 1))
                continue
            return r
        except requests.RequestException as e:
            if attempt == 3:
                raise
            log("  retry", url, e)
            time.sleep(2 * (attempt + 1))


# --------------------------------------------------------------------------- URLs

def unwrap_google(url):
    """https://www.google.com/url?q=X&sa=D... -> X"""
    if not url:
        return url
    p = urlparse(url)
    if p.netloc in ("www.google.com", "google.com") and p.path == "/url":
        q = parse_qs(p.query).get("q")
        if q:
            return q[0]
    return url


def internal_path(url):
    """Return the site-relative path for an internal URL, else None."""
    if url is None:
        return None
    url = unwrap_google(url.strip())
    if url.startswith("#"):
        return None
    p = urlparse(url)
    if p.scheme and p.scheme not in ("http", "https"):
        return None
    if p.netloc and p.netloc.lower() != HOST:
        return None
    if not p.netloc and not url.startswith("/"):
        return None
    path = p.path or "/"
    if path != "/":
        path = path.rstrip("/")
    return path


def site_link(url):
    """Rewrite a link for the clean content: internal stays site-relative
    (keeping #fragment), Google redirects are unwrapped."""
    url = unwrap_google(url)
    path = internal_path(url)
    if path is not None:
        frag = urlparse(url).fragment
        return path + ("#" + frag if frag else "")
    return url


def page_dir(base, path):
    return base if path == "/" else base / path.strip("/")


def rel_prefix(path):
    """Prefix from content/<path>/index.html back to the repo root."""
    depth = 0 if path == "/" else len(path.strip("/").split("/"))
    return "../" * (depth + 1)


def slug_for(path):
    return "home" if path == "/" else path.strip("/").replace("/", "--")


# --------------------------------------------------------------------------- assets

class Assets:
    def __init__(self):
        self.manifest = {}
        if MANIFEST.exists():
            self.manifest = json.loads(MANIFEST.read_text())
        self.counters = {}
        self.by_url = {}

    def save_manifest(self):
        MANIFEST.write_text(json.dumps(self.manifest, indent=1, sort_keys=True) + "\n")

    def _store(self, data, folder, stem, ext, kind):
        sha = hashlib.sha256(data).hexdigest()
        if sha in self.manifest and (ROOT / self.manifest[sha]).exists():
            return self.manifest[sha]
        n = 1
        while True:
            name = f"{stem}{'' if n == 1 and kind == 'file' else '-%02d' % n}{ext}"
            target = folder / name
            rel = str(target.relative_to(ROOT))
            if rel not in self.manifest.values() and not target.exists():
                break
            n += 1
        folder.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
        self.manifest[sha] = rel
        return rel

    def image(self, url, page_path):
        """Download an image (largest size) and return its repo-relative path."""
        if url in self.by_url:
            return self.by_url[url]
        candidates = []
        p = urlparse(url)
        if p.netloc.endswith("googleusercontent.com"):
            base = re.sub(r"=[a-z0-9-]+$", "", url, flags=re.I)
            candidates = [base + "=s0", url, base]
        elif p.netloc == "drive.google.com" and p.path == "/thumbnail":
            fid = parse_qs(p.query).get("id", [""])[0]
            candidates = [f"https://drive.google.com/thumbnail?id={fid}&sz=w4000", url]
        else:
            candidates = [url]
        for c in candidates:
            r = get(c)
            ct = r.headers.get("content-type", "").split(";")[0]
            if r.status_code == 200 and ct.startswith("image/"):
                ext = mimetypes.guess_extension(ct) or ".img"
                ext = {".jpe": ".jpg", ".jpeg": ".jpg"}.get(ext, ext)
                rel = self._store(r.content, IMAGES, slug_for(page_path), ext, "image")
                self.by_url[url] = rel
                return rel
        log("  !! image failed", url[:120])
        self.by_url[url] = None
        return None

    def file(self, data, name):
        return self._store(data, FILES, Path(name).stem, Path(name).suffix, "file")


# --------------------------------------------------------------------------- drive

def drive_download(file_id, kind):
    """Return (bytes, filename) or (None, reason)."""
    if kind == "document":
        r = get(f"https://docs.google.com/document/d/{file_id}/export?format=pdf")
    elif kind == "presentation":
        r = get(f"https://docs.google.com/presentation/d/{file_id}/export/pdf")
    elif kind == "spreadsheet":
        r = get(f"https://docs.google.com/spreadsheets/d/{file_id}/export?format=xlsx")
    else:
        r = get(f"https://drive.usercontent.google.com/download?id={file_id}&export=download&confirm=t")
    ct = r.headers.get("content-type", "")
    if r.status_code != 200 or ct.startswith("text/html"):
        return None, f"not public or not downloadable (HTTP {r.status_code}, {ct.split(';')[0]})"
    cd = r.headers.get("content-disposition", "")
    m = re.search(r"filename\*=UTF-8''([^;]+)", cd) or re.search(r'filename="([^"]+)"', cd)
    name = unquote(m.group(1)) if m else f"{file_id}{mimetypes.guess_extension(ct.split(';')[0]) or ''}"
    name = re.sub(r"[^A-Za-z0-9._-]+", "-", name).strip("-")
    return r.content, name


def drive_id_kind(url):
    """Recognise Drive / Docs URLs. Returns (id, kind) or (None, None)."""
    p = urlparse(url)
    if p.netloc == "docs.google.com":
        m = re.match(r"/(document|spreadsheets|presentation|forms)/d/([^/]+)", p.path)
        if m:
            kind = {"spreadsheets": "spreadsheet"}.get(m.group(1), m.group(1))
            return m.group(2), kind
    if p.netloc == "drive.google.com":
        m = re.match(r"/file/d/([^/]+)", p.path)
        if m:
            return m.group(1), "file"
        m = re.match(r"/drive/(?:u/\d+/)?folders/([^/?]+)", p.path)
        if m:
            return m.group(1), "folder"
        q = parse_qs(p.query)
        if "id" in q:
            return q["id"][0], "file"
    return None, None


def sheet_table(sheet_id):
    """Fetch a public sheet as CSV. Returns (csv_text, <table> html) or (None, reason)."""
    r = get(f"https://docs.google.com/spreadsheets/d/{sheet_id}/export?format=csv")
    if r.status_code != 200 or not r.headers.get("content-type", "").startswith("text/csv"):
        return None, f"HTTP {r.status_code}"
    text = r.content.decode("utf-8")
    rows = [row for row in csv.reader(io.StringIO(text))]
    # drop fully empty trailing rows / columns
    while rows and not any(c.strip() for c in rows[-1]):
        rows.pop()
    width = max((max((i + 1 for i, c in enumerate(row) if c.strip()), default=0) for row in rows), default=0)
    out = ["<table>", "<tbody>"]
    for row in rows:
        cells = (row + [""] * width)[:width]
        out.append("<tr>" + "".join(f"<td>{html.escape(c)}</td>" for c in cells) + "</tr>")
    out += ["</tbody>", "</table>"]
    return text, "\n".join(out)


# --------------------------------------------------------------------------- clean HTML

def embed_title(code):
    m = re.search(r"<title>(.*?)</title>", code, re.S | re.I)
    return html.unescape(m.group(1).strip()) if m else "Embedded content"


def clean_code_tables(code):
    """Turn a custom HTML embed into clean tables. Returns html or None."""
    soup = BeautifulSoup(code, "lxml")
    tables = soup.find_all("table")
    if not tables:
        return None
    parts = []
    for t in tables:
        parts.append(convert_fragment(t))
    return "\n".join(parts)


def convert_fragment(node):
    """Clean conversion for embed-code fragments (tables etc.)."""
    if isinstance(node, Comment):
        return ""
    if isinstance(node, NavigableString):
        return html.escape(str(node), quote=False)
    if node.name in DROP:
        return ""
    inner = "".join(convert_fragment(c) for c in node.children)
    name = node.name
    if name == "span" and "description" in (node.get("class") or []):
        return f"<small>{inner.strip()}</small>"
    if name in ("th", "td"):
        attrs = "".join(f' {a}="{node[a]}"' for a in ("colspan", "rowspan") if node.get(a))
        cell = re.sub(r"\s+", " ", inner).strip()
        return f"<{name}{attrs}>{cell}</{name}>"
    if name in BLOCK_KEEP or name in INLINE_KEEP:
        if name == "br":
            return "<br>"
        if name == "a":
            return f'<a href="{html.escape(site_link(node.get("href", "")))}">{inner}</a>'
        if name in ("table", "thead", "tbody", "tr"):
            return f"<{name}>\n{inner.strip()}\n</{name}>\n"
        return f"<{name}>{inner}</{name}>"
    return inner


class Converter:
    """Converts one Google Sites page into clean semantic HTML."""

    def __init__(self, page_path, assets):
        self.path = page_path
        self.assets = assets
        self.prefix = rel_prefix(page_path)
        self.images = []
        self.links = []
        self.embeds = []
        self.files = []
        self.embed_n = 0

    # -- helpers
    def img_src(self, url):
        rel = self.assets.image(url, self.path)
        if rel:
            if rel not in self.images:
                self.images.append(rel)
            return self.prefix + rel
        return url

    def add_link(self, href, text):
        self.links.append({"href": href, "text": text,
                           "internal": internal_path(href) is not None})

    # -- embeds
    def embed_html(self, el):
        """el is an element carrying data-code or data-embed-doc-id."""
        self.embed_n += 1
        n = self.embed_n
        if el.has_attr("data-code"):
            code = el["data-code"]
            name = f"{slug_for(self.path)}-embed-{n:02d}.html"
            EMBEDS.mkdir(parents=True, exist_ok=True)
            (EMBEDS / name).write_text(code)
            src = f"assets/embeds/{name}"
            iframes = re.findall(r'<iframe[^>]+src="([^"]+)"', code)
            tables = clean_code_tables(code)
            info = {"type": "custom-html", "code_file": src, "iframe_targets": iframes,
                    "converted_to": "table" if tables else "iframe"}
            yt = [u for u in iframes if "youtube" in u or "youtu.be" in u]
            if yt:
                info["type"] = "youtube"
            self.embeds.append(info)
            if tables:
                return (f'<figure class="embed" data-embed-type="custom-html" '
                        f'data-embed-source="{self.prefix}{src}">\n{tables}</figure>\n')
            return (f'<figure class="embed" data-embed-type="{info["type"]}" '
                    f'data-embed-source="{self.prefix}{src}">'
                    f'<iframe src="{self.prefix}{src}" title="{html.escape(embed_title(code))}" '
                    f'allow="serial; clipboard-write" loading="lazy"></iframe></figure>\n')

        doc_id = el.get("data-embed-doc-id")
        open_url = el.get("data-embed-open-url", "")
        inner = el if el.has_attr("data-src") else el.find(attrs={"data-src": True})
        data_src = inner.get("data-src", "") if inner else ""
        fid, kind = drive_id_kind(data_src or open_url)
        fid = fid or doc_id
        tile = el.find_parent("div", class_="tyJCtd") or el
        t_el = tile.find(class_="pB4Yfc")
        etitle = t_el.get_text(" ", strip=True) if t_el else ""
        cap = f"<figcaption>{html.escape(etitle)}</figcaption>\n" if etitle else ""
        info = {"type": "google-sheet" if kind == "spreadsheet" else f"google-{kind or 'drive'}", "id": fid, "title": etitle,
                "open_url": open_url, "embed_url": data_src}
        if kind == "spreadsheet":
            src_url = f"https://docs.google.com/spreadsheets/d/{fid}"
            csv_text, table = sheet_table(fid)
            if csv_text is not None:
                rel = self.assets.file(csv_text.encode("utf-8"), f"sheet-{slug_for(self.path)}.csv")
                info.update(converted_to="table", csv=rel, source=src_url)
                self.files.append(rel)
                self.embeds.append(info)
                return (f'<figure class="embed" data-embed-type="google-sheet" '
                        f'data-embed-source="{src_url}" data-csv="{self.prefix}{rel}">\n'
                        f'<!-- Converted from public Google Sheet {src_url} -->\n{cap}{table}\n</figure>\n')
            info.update(converted_to="iframe", error=table)
            self.embeds.append(info)
            return (f'<figure class="embed" data-embed-type="google-sheet" data-embed-source="{src_url}">{cap}'
                    f'<iframe src="{html.escape(data_src)}" loading="lazy"></iframe></figure>\n')

        data, name = drive_download(fid, kind or "file")
        title = el.get("aria-label") or ""
        if data is not None:
            rel = self.assets.file(data, name)
            self.files.append(rel)
            info.update(file=rel, downloaded=True)
            self.embeds.append(info)
            label = etitle or Path(name).stem.replace("-", " ")
            return (f'<figure class="embed" data-embed-type="{info["type"]}" '
                    f'data-embed-source="{html.escape(open_url or data_src)}" data-file="{self.prefix}{rel}">'
                    f'<iframe src="{html.escape(data_src)}" loading="lazy"></iframe>'
                    f'<figcaption><a href="{self.prefix}{rel}">{html.escape(label)}</a></figcaption></figure>\n')
        info.update(downloaded=False, error=name)
        self.embeds.append(info)
        return (f'<figure class="embed" data-embed-type="{info["type"]}" '
                f'data-embed-source="{html.escape(open_url or data_src)}">{cap}'
                f'<iframe src="{html.escape(data_src)}" loading="lazy"></iframe></figure>\n')

    # -- main walker
    def node(self, n):
        if isinstance(n, Comment):
            return ""
        if isinstance(n, NavigableString):
            return html.escape(str(n), quote=False)
        if not isinstance(n, Tag) or n.name in DROP:
            return ""
        cls = n.get("class") or []
        # "Copy heading link" widget inside headings
        if "PPhIP" in cls or n.get("aria-label") == "Copy heading link":
            return ""
        # tile containing an embed
        if n.has_attr("data-code") or n.has_attr("data-embed-doc-id"):
            return self.embed_html(n)
        if n.name == "div" and "tyJCtd" in cls:
            emb = n.find_all(lambda t: t.has_attr("data-code") or t.has_attr("data-embed-doc-id"))
            if emb:
                return "".join(self.embed_html(e) for e in emb)
        if n.name == "iframe":
            src = n.get("src") or n.get("data-src") or ""
            if src and "gstatic" not in src and "googleusercontent" not in src:
                self.embeds.append({"type": "iframe", "src": src})
                return f'<figure class="embed" data-embed-type="iframe"><iframe src="{html.escape(src)}"></iframe></figure>\n'
            return ""
        # layout row: several columns side by side
        if n.name == "div" and "LS81yb" in cls:
            cols = [c for c in n.find_all("div", recursive=False)]
            rendered = [self.children(c).strip() for c in cols]
            rendered = [r for r in rendered if r]
            if len(rendered) > 1:
                return ('<div class="row">\n' +
                        "".join(f'<div class="col">\n{r}\n</div>\n' for r in rendered) + "</div>\n")
            return (rendered[0] + "\n") if rendered else ""
        if n.name == "img":
            src = n.get("src") or ""
            if not src or "gstatic.com/images/icons" in src:
                return ""
            alt = n.get("alt") or n.get("aria-label") or ""
            return f'<img src="{html.escape(self.img_src(src))}" alt="{html.escape(alt)}">'
        if n.name in ("h1", "h2", "h3", "h4", "h5", "h6"):
            hid = (n.get("id") or "").removesuffix("_l")
            inner = self.children(n).strip()
            if not inner:
                return ""
            idattr = f' id="{html.escape(hid)}"' if hid else ""
            return f"<{n.name}{idattr}>{inner}</{n.name}>\n"
        if n.name == "p":
            inner = self.children(n)
            if n.get("role") == "presentation" and n.parent and n.parent.name == "li":
                return inner
            if not inner.strip() or inner.strip() == "&nbsp;":
                return "<p></p>\n" if inner else ""
            return f"<p>{inner}</p>\n"
        if n.name == "li":
            return f"<li>{self.children(n).strip()}</li>\n"
        if n.name in ("ul", "ol"):
            return f"<{n.name}>\n{self.children(n)}</{n.name}>\n"
        if n.name == "a":
            href = n.get("href") or ""
            if href.startswith("#h.") or not href:
                return self.children(n)
            new = site_link(href)
            text = n.get_text(" ", strip=True)
            self.add_link(new, text)
            inner = self.children(n)
            m = re.fullmatch(r"\s*<p>(.*?)</p>\s*", inner, re.S)
            if m:  # Google Sites button: <a><p>label</p></a>
                return f'<p><a class="button" href="{html.escape(new)}">{m.group(1)}</a></p>\n'
            return f'<a href="{html.escape(new)}">{inner}</a>'
        if n.name == "br":
            return "<br>"
        if n.name == "span":
            inner = self.children(n)
            style = (n.get("style") or "").replace(" ", "").lower()
            if not inner.strip():
                return inner
            if re.search(r"font-weight:(bold|[6-9]00)", style):
                inner = f"<strong>{inner}</strong>"
            if "font-style:italic" in style:
                inner = f"<em>{inner}</em>"
            if "vertical-align:super" in style:
                inner = f"<sup>{inner}</sup>"
            if "vertical-align:sub" in style:
                inner = f"<sub>{inner}</sub>"
            return inner
        if n.name in INLINE_KEEP:
            return f"<{n.name}>{self.children(n)}</{n.name}>"
        if n.name in BLOCK_KEEP:
            return f"<{n.name}>{self.children(n)}</{n.name}>\n"
        return self.children(n)

    def children(self, n):
        return "".join(self.node(c) for c in n.children)

    def section(self, sec):
        bg = None
        for el in sec.find_all(style=re.compile(r"background-image")):
            if el.find_parent(lambda t: t.has_attr("data-embed-doc-id")) or el.has_attr("data-embed-doc-id"):
                continue
            m = re.search(r"url\(([^)]+)\)", el["style"])
            if m and "drive.google.com/thumbnail" not in m.group(1):
                bg = self.img_src(html.unescape(m.group(1).strip("'\"")))
                break
        body = self.children(sec).strip()
        body = re.sub(r"(<p></p>\n){2,}", "<p></p>\n", body)
        if not body and not bg:
            return ""
        attrs = f' data-background="{html.escape(bg)}"' if bg else ""
        return f"<section{attrs}>\n{body}\n</section>\n"


def tidy(s):
    s = s.replace(" ", "&nbsp;")
    s = re.sub(r"\n{3,}", "\n\n", s)
    return s


# --------------------------------------------------------------------------- nav

def parse_nav(soup):
    nav = soup.find("nav", attrs={"role": "navigation"}) or soup.find("nav")

    def walk(ul):
        items = []
        for li in ul.find_all("li", recursive=False):
            a = li.find("a", attrs={"data-level": True})
            if not a:
                continue
            raw = a.get("data-url") or a.get("href")
            target = unwrap_google(raw)
            ipath = internal_path(raw)
            item = OrderedDict()
            item["title"] = a.get_text(" ", strip=True)
            if a.get("data-type") == "2" or ipath is None:
                item["type"] = "external"
                item["url"] = target
            else:
                item["type"] = "page"
                item["path"] = ipath
            sub = li.find("ul")
            if sub:
                kids = walk(sub)
                if kids:
                    item["children"] = kids
            items.append(item)
        return items

    return walk(nav.find("ul")) if nav else []


def flatten(items, parent=None, out=None):
    out = [] if out is None else out
    for it in items:
        out.append((it, parent))
        flatten(it.get("children", []), it, out)
    return out


# --------------------------------------------------------------------------- main

def fetch_page(path):
    r = get(BASE + path)
    final = urlparse(r.url)
    return r.status_code, r.text, (final.path.rstrip("/") or "/")


def main():
    assets = Assets()
    for d in (RAW, CONTENT):
        d.mkdir(exist_ok=True)

    queue = ["/"]
    seen = set()
    pages = OrderedDict()
    nav_tree = None
    footer_html = None
    site_logo = None

    first = True
    while queue:
        path = queue.pop(0)
        if path in seen:
            continue
        seen.add(path)
        status, text, final = fetch_page(path)
        log(f"[{len(seen):2d}] {status} {path}" + (f" -> {final}" if final != path else ""))
        if status != 200:
            pages[path] = {"path": path, "status": status}
            continue
        rd = page_dir(RAW, path)
        rd.mkdir(parents=True, exist_ok=True)
        (rd / "index.html").write_text(text)

        soup = BeautifulSoup(text, "lxml")
        if first:
            nav_tree = parse_nav(soup)
            for it, _ in flatten(nav_tree):
                if it["type"] == "page" and it["path"] not in seen:
                    queue.append(it["path"])
            queue += [p for p in EXTRA_SEEDS if p not in queue]
            logo = soup.select_one("nav a img, header img")
            if logo and logo.get("src"):
                site_logo = assets.image(logo["src"], "/site-logo")
            first = False

        conv = Converter(path, assets)
        title = (soup.title.string or "").strip() if soup.title else ""
        main_secs = [s for s in soup.find_all("section") if not s.find_parent("footer")]
        body = "".join(conv.section(s) for s in main_secs)

        if footer_html is None:
            f = soup.find("footer")
            if f:
                fc = Converter("/", assets)
                footer_html = "".join(fc.section(s) for s in f.find_all("section"))
                footer_links = fc.links

        last_upd = soup.find(attrs={"data-last-updated-at-time": True})
        doc = (f'<!doctype html>\n<html lang="en">\n<head>\n<meta charset="utf-8">\n'
               f'<title>{html.escape(title)}</title>\n'
               f'<link rel="canonical" href="{BASE}{path}">\n</head>\n<body>\n'
               f'<main data-path="{path}">\n{body}</main>\n</body>\n</html>\n')
        cd = page_dir(CONTENT, path)
        cd.mkdir(parents=True, exist_ok=True)
        (cd / "index.html").write_text(tidy(doc))

        headings = [{"level": int(h.name[1]), "text": h.get_text(" ", strip=True),
                     "id": (h.get("id") or "").removesuffix("_l")}
                    for s in main_secs for h in s.find_all(re.compile(r"^h[1-6]$"))
                    if h.get_text(strip=True)]
        pages[path] = OrderedDict(
            path=path,
            title=title,
            status=status,
            last_updated=(last_upd["data-last-updated-at-time"] if last_upd else None),
            raw=str((rd / "index.html").relative_to(ROOT)),
            content=str((cd / "index.html").relative_to(ROOT)),
            headings=headings,
            images=conv.images,
            files=conv.files,
            embeds=conv.embeds,
            links=conv.links,
        )
        # follow internal links found in the page body
        for l in conv.links:
            ip = internal_path(l["href"])
            if ip and ip not in seen and ip not in queue:
                queue.append(ip)
        assets.save_manifest()
        time.sleep(0.2)

    # linked Drive / Docs files (not embeds)
    drive_links = OrderedDict()
    for p in pages.values():
        for l in p.get("links", []):
            fid, kind = drive_id_kind(l["href"])
            if fid and fid not in drive_links:
                drive_links[fid] = {"id": fid, "kind": kind, "url": l["href"], "pages": []}
            if fid:
                drive_links[fid]["pages"].append(p["path"])
    for fid, d in drive_links.items():
        if d["kind"] == "folder":
            d.update(downloaded=False, note="Drive folder: listing not downloadable without API access")
            continue
        data, name = drive_download(fid, d["kind"])
        if data is None:
            d.update(downloaded=False, note=name)
        else:
            d.update(downloaded=True, file=assets.file(data, name))
    assets.save_manifest()

    # site.json
    nav_paths = {it["path"] for it, _ in flatten(nav_tree) if it["type"] == "page"}
    titles = {it["path"]: it["title"] for it, _ in flatten(nav_tree) if it["type"] == "page"}
    parents = {it["path"]: (par["path"] if par and par.get("path") else None)
               for it, par in flatten(nav_tree) if it["type"] == "page"}
    for p in pages.values():
        p["nav_title"] = titles.get(p["path"])
        p["nav_parent"] = parents.get(p["path"])
        p["in_menu"] = p["path"] in nav_paths
    hidden = [{"path": p["path"], "title": p.get("title"),
               "note": ("site root, serves the same content as /documentation-home"
                        if p["path"] == "/" else "reachable but not in the menu")}
              for p in pages.values() if not p["in_menu"]]

    if footer_html is not None:
        (CONTENT / "_footer.html").write_text(tidy(footer_html))

    site = OrderedDict(
        source=BASE,
        scraped_at=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        site_logo=site_logo,
        footer={"content": "content/_footer.html", "links": footer_links if footer_html else []},
        navigation=nav_tree,
        hidden_pages=hidden,
        linked_drive_files=list(drive_links.values()),
        pages=list(pages.values()),
    )
    (ROOT / "site.json").write_text(json.dumps(site, indent=2, ensure_ascii=False) + "\n")

    n_img = len(list(IMAGES.glob("*"))) if IMAGES.exists() else 0
    n_files = len(list(FILES.glob("*"))) if FILES.exists() else 0
    log(f"done: {len(pages)} pages, {n_img} images, {n_files} files")


if __name__ == "__main__":
    main()
