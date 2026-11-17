#!/usr/bin/env python3
"""Turn a public Google Doc into a clean content page for the site.

Usage:
  .venv/bin/python tools/convert_gdoc.py <doc_id> <site path> [image prefix] [pdf url]

Example (the "Rodec 100 Series" document shown on /rodec-100-series):
  .venv/bin/python tools/convert_gdoc.py 19kwjPZSFMgWiYLjbOIr7Uig1V3lByOBdw6qnzmAiuVM /rodec-100-series 100-series /assets/files/Rodec-100-Series.pdf

Downloads the document as a zip export (HTML + images), and writes
  src/content/<path>/index.html   clean HTML in the same format as content/
                                  (tools/build.py prefers it over content/)
  src/img/<prefix>/*.webp         the images, lossless WebP (photos lossy)
The headings shift one level down (the page title is the h1). Bold, italic
and links are kept; Google redirect links are unwrapped; empty paragraphs,
rules, inline styles and classes are dropped.
"""
import html
import io
import re
import sys
import zipfile
from pathlib import Path
from urllib.parse import urlparse, parse_qs

import requests
from bs4 import BeautifulSoup, NavigableString, Tag
from PIL import Image

ROOT = Path(__file__).resolve().parent.parent


def class_styles(soup):
    """Class name -> set of {'b', 'i', 'u'} from the export's <style>."""
    css = "".join(st.get_text() for st in soup.find_all("style"))
    out = {}
    for sel, body in re.findall(r"\.([\w-]+)\{([^}]*)\}", css):
        f = set()
        if re.search(r"font-weight:\s*(700|bold)", body):
            f.add("b")
        if "font-style:italic" in body.replace(" ", ""):
            f.add("i")
        out[sel] = f
    return out


def unwrap(url):
    p = urlparse(url)
    if p.netloc.endswith("google.com") and p.path == "/url":
        return parse_qs(p.query).get("q", [url])[0]
    return url


def main():
    doc_id, site_path = sys.argv[1], sys.argv[2]
    prefix = sys.argv[3] if len(sys.argv) > 3 else site_path.strip("/").replace("/", "-")
    pdf = sys.argv[4] if len(sys.argv) > 4 else None   # optional link to a PDF copy
    r = requests.get(f"https://docs.google.com/document/d/{doc_id}/export?format=zip", timeout=120)
    r.raise_for_status()
    z = zipfile.ZipFile(io.BytesIO(r.content))
    html_name = next(n for n in z.namelist() if n.endswith(".html"))
    soup = BeautifulSoup(z.read(html_name).decode("utf-8"), "lxml")
    styles = class_styles(soup)

    img_dir = ROOT / "src" / "img" / prefix
    img_dir.mkdir(parents=True, exist_ok=True)
    img_n = 0
    img_map = {}

    def save_image(src):
        nonlocal img_n
        if src in img_map:
            return img_map[src]
        img_n += 1
        im = Image.open(io.BytesIO(z.read(src)))
        photo = src.lower().endswith((".jpg", ".jpeg"))
        im = im.convert("RGB") if photo or im.mode not in ("RGBA", "LA") else im.convert("RGBA")
        if im.width > 1800:
            im = im.resize((1800, round(im.height * 1800 / im.width)), Image.LANCZOS)
        name = f"{prefix}-{img_n:02d}.webp"
        if photo:
            im.save(img_dir / name, "WEBP", quality=88, method=6)
        else:
            im.save(img_dir / name, "WEBP", lossless=True, method=6)
        img_map[src] = (f"/assets/{prefix}/{name}", im.width, im.height)
        return img_map[src]

    def inline(node):
        if isinstance(node, NavigableString):
            return html.escape(str(node), quote=False)
        if not isinstance(node, Tag):
            return ""
        if node.name == "br":
            return "<br>"
        if node.name == "img":
            return ""
        inner = "".join(inline(c) for c in node.children)
        if node.name == "a" and node.get("href"):
            href = unwrap(node["href"])
            if href.startswith("#"):
                return inner
            return f'<a href="{html.escape(href)}">{inner}</a>'
        if node.name == "span" and inner.strip():
            f = set()
            for c in node.get("class") or []:
                f |= styles.get(c, set())
            if "i" in f:
                inner = f"<em>{inner}</em>"
            if "b" in f:
                inner = f"<strong>{inner}</strong>"
        return inner

    def text_of(node):
        t = "".join(inline(c) for c in node.children)
        t = re.sub(r"</strong>(\s*)<strong>", r"\1", t)
        t = t.replace(" ", " ")
        return re.sub(r"[ \t]+", " ", t).strip()

    out = []
    body = soup.body
    blocks = [c for c in body.children if isinstance(c, Tag)]
    meta = ""
    for el in blocks:
        name = el.name
        imgs = el.find_all("img")
        # the document footer (version line) sits in a trailing div
        if name == "div":
            t = re.sub(r"\s+", " ", el.get_text(" ", strip=True))
            if t:
                meta = t
            continue
        if name == "hr":
            continue
        if name in ("h1", "h2", "h3", "h4"):
            t = text_of(el)
            if t:
                # doc h1 -> h2, h2 and h3 -> h3 (the doc skips a level)
                lvl = {"h1": 2, "h2": 3}.get(name, 3)
                t = re.sub(r"</?strong>", "", t)
                hid = re.sub(r"[^a-z0-9]+", "-", re.sub(r"<[^>]+>", "", t).lower()).strip("-")
                out.append(f'<h{lvl} id="{hid}">{t}</h{lvl}>')
            continue
        if name == "table":
            rows = []
            for i, tr in enumerate(el.find_all("tr")):
                cells = [text_of(td) for td in tr.find_all(["td", "th"])]
                tag = "th" if i == 0 else "td"
                rows.append("<tr>" + "".join(f"<{tag}>{re.sub(r'</?strong>', '', c) if tag == 'th' else c}</{tag}>"
                                             for c in cells) + "</tr>")
            out.append("<table>\n<thead>\n" + rows[0] + "\n</thead>\n<tbody>\n" + "\n".join(rows[1:]) + "\n</tbody>\n</table>")
            continue
        if name in ("ul", "ol"):
            items = [f"<li>{text_of(li)}</li>" for li in el.find_all("li", recursive=False)]
            out.append(f"<{name}>\n" + "\n".join(items) + f"\n</{name}>")
            continue
        if name == "p":
            for im in imgs:
                url, w, h = save_image(im["src"])
                out.append(f'<figure class="doc-fig"><a href="{url}"><img src="{url}" alt="" width="{w}" height="{h}"></a></figure>')
            t = text_of(el)
            if t:
                out.append(f"<p>{t}</p>")

    if meta:
        meta = re.sub(r"\s+p$", "", meta)                 # trailing page number field
        meta = re.sub(r"\s+(V \d[\d.]*)\s+", r" · \1 · ", meta)
        meta = meta.replace(" www.rodec.com", "")
        out.append(f'<p class="doc-meta">{html.escape(meta)}</p>')

    # group consecutive figures into one row
    joined = "\n".join(out)
    joined = re.sub(r'((?:<figure class="doc-fig">.*?</figure>\n?){2,})',
                    lambda m: '<div class="doc-figs">\n' + m.group(1).strip() + "\n</div>", joined)
    # a short paragraph right before a group of figures is the group's title
    joined = re.sub(r'<p>([^<]{1,40})</p>\n(<div class="doc-figs">)', r'<p class="fig-title">\1</p>\n\2', joined)
    # bare links to this documentation site become internal links
    joined = re.sub(r'<p>https://documentation\.rodec\.com(/[^<\s]*)</p>', r'<p><a href="\1">documentation.rodec.com\1</a></p>', joined)
    # "See:" followed by link-only paragraphs -> a list
    def see(m):
        links = re.findall(r'<p>(<a [^>]+>.*?</a>)</p>', m.group(2))
        return f"<p>{m.group(1)}</p>\n<ul>\n" + "\n".join(f"<li>{l}</li>" for l in links) + "\n</ul>"
    joined = re.sub(r'<p>(See:)</p>\n((?:<p><a [^>]+>.*?</a></p>\n?)+)', see, joined)
    # decimal commas in tables (91,44 -> 91.44), like the rest of the table
    joined = re.sub(r'(<t[dh]>(?:<strong>)?\d+),(\d+)', r'\1.\2', joined)
    # a short paragraph right before a figure is its caption
    joined = re.sub(r'<p>([^<]{1,40})</p>\n(<figure class="doc-fig">)(<a [^>]+><img [^>]+></a>)</figure>',
                    r'\2\3<figcaption>\1</figcaption></figure>', joined)

    if pdf:
        joined = f'<p><a class="button" href="{pdf}">Download as PDF</a></p>\n' + joined
    page = (f'<!doctype html>\n<html lang="en">\n<head>\n<meta charset="utf-8">\n'
            f'<title>converted from Google Doc {doc_id}</title>\n</head>\n<body>\n'
            f'<main data-path="{site_path}" data-source="https://docs.google.com/document/d/{doc_id}">\n'
            f"<section>\n{joined}\n</section>\n</main>\n</body>\n</html>\n")
    dest = ROOT / "src" / "content" / site_path.strip("/") / "index.html"
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(page)
    print(f"wrote {dest.relative_to(ROOT)}, {img_n} images in src/img/{prefix}/")


if __name__ == "__main__":
    main()
