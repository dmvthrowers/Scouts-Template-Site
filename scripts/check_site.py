#!/usr/bin/env python3
"""Check the built site in _site/ for problems. Run after build.py:

    python3 build.py && python3 scripts/check_site.py

Checks every page for: broken internal links and images, images without alt text or
size, invalid JSON-LD, missing title/description, the skip link, main#main-content,
and that the header, menu, and footer are identical on every page.
Security: every page has the Content Security Policy and referrer tags, with no
'unsafe-inline', no inline styles, scripts or event handlers, and no http:// links.
Privacy: unless site.jsonc sets photos.first_names_only to false, flags text that looks like a
child's full name ("Emma Johnson"): a common first name followed by a capitalized word. Names in the
leaders list and in photos.allowed_names are fine. It is a guard, not a guarantee: read your pages too.
With --real (your copy's deploy workflow), it also fails while the template's sample content
(example.org addresses, the Maple Street sample club) is still on the site.
Exits non-zero if anything fails. No installs needed.
"""
import json
import re
import sys
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urlparse, unquote

ROOT = Path(__file__).resolve().parent.parent
args = sys.argv[1:]
# --real: this is someone's live site, so the template's sample content must be gone.
# Your copy's deploy workflow passes it; the template's own showcase doesn't.
REAL = "--real" in args
args = [a for a in args if a != "--real"]
# Text that only appears in the template's sample settings. Reserved example domains never belong
# on a real site.
SAMPLE_MARKERS = ("example.org", "example.com", "Maple Street Kids Club", "Jordan Example", "Springfield Community Center")
# Optional: check_site.py [SITE_DIR [BASE_PATH]] (used for the showcase's example sites)
SITE = (ROOT / args[0]).resolve() if args else ROOT / "_site"
base_file = ROOT / ".build-base-path"
BASE = args[1] if len(args) > 1 else (base_file.read_text().strip() if base_file.exists() else "/")
errors = []

# Common US first names that are not also everyday words or places (so "Jackson Park" and "Grace Notes"
# are not flagged). A guard against careless captions, not a name detector.
FIRST_NAMES = set("""
Aaliyah Abigail Adam Adrian Aiden Alexander Alexis Alice Alyssa Amelia Amy Andrew Angel Anna Anthony Aria Ariana
Arthur Ashley Audrey Aubrey Ava Benjamin Bella Brandon Brayden Brian Brianna Caleb Camila Carter Charles Charlotte
Chloe Christian Christopher Claire Colton Connor Daniel David Dylan Eleanor Elijah Elizabeth Ella Ellie Emily Emma
Ethan Eva Evan Evelyn Gabriel Gavin Hailey Hannah Harper Henry Isaac Isabella Isaiah Jack Jacob Jaden James Jasmine
Jayden Jeremiah Jessica Joel John Jonathan Joseph Joshua Josiah Julia Julian Kaitlyn Katherine Kayla Kevin Kylie
Landon Lauren Layla Leah Leo Levi Liam Lillian Lily Logan Lucas Lucy Luke Madeline Maya Mia Michael Mila Natalie
Nathan Nevaeh Nicholas Noah Nora Olivia Owen Penelope Riley Robert Ryan Samantha Samuel Sarah Savannah Scarlett
Sebastian Sofia Sophia Sophie Stella Tyler Victoria Violet Vivian William Wyatt Xavier Zachary Zoe Zoey
""".split())
# Words that follow a first name when it is really a place or group ("Harper Elementary", "Riley Park").
PLACE_WORDS = set("""
Academy Avenue Baptist Bridge Camp Center Church Circle Club Community Court Creek Drive Elementary Field Fields Forest
Garden Gardens Hall High Hill Hills Lake Lane Library Lodge Middle Park Pavilion Pool Preschool Ridge River Road School
Scouts Square Station Street Temple Trail Troop Pack Way Woods
""".split())
SURNAME = re.compile(r"\b([A-Z][a-z]{2,})\s+([A-Z][a-z'\-]{2,})\b")


class Text(HTMLParser):
    """Visible text of a page (plus img alt text), minus the leaders list, footer, scripts and styles."""
    def __init__(self):
        super().__init__()
        self.parts, self.skip, self.depth, self.stack = [], 0, 0, []

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        skipping = tag in ("script", "style", "title", "footer") or "leader-list" in (a.get("class") or "")
        if tag not in ("br", "img", "meta", "link", "input", "hr"):
            self.stack.append(skipping)
            self.skip += skipping
        if tag == "img" and a.get("alt"):
            self.parts.append(a["alt"])

    def handle_endtag(self, tag):
        if self.stack and tag not in ("br", "img", "meta", "link", "input", "hr"):
            self.skip -= self.stack.pop()

    def handle_data(self, d):
        if not self.skip:
            self.parts.append(d)


class Page(HTMLParser):
    def __init__(self):
        super().__init__()
        self.refs, self.imgs, self.svgs, self.ids, self.ld = [], [], [], set(), []
        self._ld = False
        self.title = False
        self.meta = {}
        self.csp = None
        self.security = []

    def handle_starttag(self, tag, attrs):
        # HTMLParser lower-cases tag and attribute names and handles any quoting style.
        a = dict(attrs)
        if a.get("id"):
            self.ids.add(a["id"])
        for k in ("href", "src"):
            if a.get(k) and tag != "iframe":
                self.refs.append(a[k])
        if tag == "img":
            self.imgs.append(a)
        if tag == "svg":
            self.svgs.append(a)
        if tag == "title":
            self.title = True
        if tag == "meta" and a.get("name"):
            self.meta[a["name"].lower()] = a.get("content", "")
        if tag == "meta" and (a.get("http-equiv") or "").lower() == "content-security-policy":
            self.csp = a.get("content") or ""
        is_ld = tag == "script" and (a.get("type") or "").lower() == "application/ld+json"
        if is_ld:
            self._ld = True
            self.ld.append("")
        if tag == "style":
            self.security.append("inline <style> block (use style.css)")
        if tag == "script" and "src" not in a and not is_ld:
            self.security.append("inline <script> (use a .js file)")
        for k, v in a.items():
            if k == "style":
                self.security.append(f"inline style on <{tag}> (use a class in style.css)")
            elif k.startswith("on"):
                self.security.append(f"inline event handler {k}= on <{tag}>")
            elif k in ("href", "src", "action") and v:
                low = v.strip().lower()
                if low.startswith("http:"):
                    self.security.append(f"insecure http:// link: {v}")
                elif low.startswith("javascript:"):
                    self.security.append(f"javascript: URL on <{tag}>")

    def handle_endtag(self, tag):
        if tag == "script":
            self._ld = False

    def handle_data(self, d):
        if self._ld:
            self.ld[-1] += d


def shared_block(html, start, end):
    i = html.find(start)
    j = html.find(end, i)
    chunk = html[i:j + len(end)] if i >= 0 and j >= 0 else ""
    chunk = chunk.replace(' aria-current="page"', "")
    chunk = re.sub(r'(href|src)="' + re.escape(BASE), r'\1="', chunk) if BASE != "/" else chunk.replace('="/', '="')
    return re.sub(r"\s+", " ", chunk).strip()


if not SITE.exists():
    sys.exit("No _site/ folder. Run: python3 build.py")

pages = sorted(SITE.glob("*.html"))
for page in pages:
    html = page.read_text(encoding="utf-8")
    p = Page()
    p.feed(html)
    err = lambda msg, n=page.name: errors.append(f"{n}: {msg}")
    if p.csp is None:
        err("missing Content-Security-Policy meta tag")
    elif "unsafe-inline" in p.csp.lower() or "unsafe-eval" in p.csp.lower():
        err("CSP allows unsafe-inline/unsafe-eval")
    if not p.meta.get("referrer"):
        err("missing referrer meta tag")
    for problem in p.security:
        err(problem)
    if not p.title:
        err("missing <title>")
    if not p.meta.get("description"):
        err("missing meta description")
    if "main-content" not in p.ids:
        err('missing <main id="main-content">')
    if 'class="skip-link"' not in html:
        err("missing skip link")
    for block in p.ld:
        try:
            json.loads(block)
        except ValueError as e:
            err(f"invalid JSON-LD: {e}")
    for img in p.imgs:
        if "alt" not in img:
            err(f"img without alt: {img.get('src')}")
        if not (img.get("width") and img.get("height")):
            err(f"img without width/height: {img.get('src')}")
    for svg in p.svgs:
        if not (svg.get("width") and svg.get("height")):
            err("inline <svg> without width/height")
    for ref in p.refs:
        if ref.strip() in ("", "mailto:", "tel:") or ref.strip().startswith(("mailto:?", "tel:?")):
            err(f"empty link target: {ref!r}")
            continue
        u = urlparse(ref)
        if u.scheme in ("http", "https", "mailto", "tel", "data") or ref.startswith("#"):
            continue
        path = unquote(u.path)
        if path.startswith(BASE):
            path = path[len(BASE):]
        elif path.startswith("/"):
            err(f"absolute link outside the site: {ref}")
            continue
        if not (SITE / (path or "index.html")).exists():
            err(f"broken link: {ref}")

privacy_file = ROOT / ".build-privacy.json"
privacy = json.loads(privacy_file.read_text()) if privacy_file.exists() and SITE == ROOT / "_site" else {}
if privacy.get("first_names_only", True):
    allowed = {n.strip().lower() for n in privacy.get("allowed_names", [])}
    for page in pages:
        t = Text()
        t.feed(page.read_text(encoding="utf-8"))
        text = re.sub(r"\s+", " ", " ".join(t.parts))
        for first, last in SURNAME.findall(text):
            if first in FIRST_NAMES and last not in PLACE_WORDS and f"{first} {last}".lower() not in allowed:
                errors.append(f'{page.name}: "{first} {last}" looks like a full name. Use first names only, '
                              'or list an adult in photos.allowed_names (or set photos.first_names_only to false).')
if REAL:
    found = sorted({m for page in pages for m in SAMPLE_MARKERS if m in page.read_text(encoding="utf-8")})
    if found:
        errors.append("the site still shows the template's sample content (" + ", ".join(found) + "). "
                      "Put your own unit's details in site.jsonc: name, meeting place, contact email and leaders.")

reference = (SITE / "about.html").read_text(encoding="utf-8")
for label, start, end in (("header", "<header", "</header>"), ("footer", "<footer", "</footer>")):
    want = shared_block(reference, start, end)
    for page in pages:
        if shared_block(page.read_text(encoding="utf-8"), start, end) != want:
            errors.append(f"{page.name}: {label} differs from about.html")

for f in SITE.rglob("*"):
    if f.is_file() and f.stat().st_size > 500_000:
        errors.append(f"{f.relative_to(SITE)} is {f.stat().st_size // 1024} KB (keep files under 500 KB)")

if errors:
    print(f"{len(errors)} problem(s):")
    for e in errors:
        print("  -", e)
    sys.exit(1)
print(f"OK: {len(pages)} pages checked, no problems found.")
