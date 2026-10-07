#!/usr/bin/env python3
"""Build the website from site.jsonc + a preset into _site/.

    python3 build.py                 # build into _site/
    python3 build.py --serve         # build, then preview at http://localhost:8000/
    python3 build.py --base-url https://example.org/   # set the public address

No installs needed: standard-library Python 3.9+ only.

How it fits together:
  site.jsonc        your settings (the only file most people edit)
  presets/*.json    starting text for each kind of group (kids club, Cub Scouts, ...)
  assets/           stylesheet, script, and your images (copied as-is)
  content/*.html    optional extra HTML added to the bottom of a page (e.g. content/about.html)
  build.py          this file: one small function per page, near the bottom
"""
import argparse
import datetime as dt
import html
import http.server
import json
import os
import re
import shutil
import struct
import sys
import zlib
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parent
OUT = ROOT / "_site"
warnings = []


# ---------------------------------------------------------------- config

def load_jsonc(path):
    """JSON that allows whole-line // comments and trailing commas."""
    # Blank out comment lines (instead of removing them) so error line numbers match the file.
    lines = ["" if l.lstrip().startswith("//") else l for l in path.read_text(encoding="utf-8").splitlines()]
    text = re.sub(r",(\s*[}\]])", r"\1", "\n".join(lines))
    try:
        return json.loads(text)
    except json.JSONDecodeError as e:
        sys.exit(f"\n{path.name} has a typo near line {e.lineno}: {e.msg}.\n"
                 "Check for a missing comma or quote on that line or the one above it.\n")


def merge(base, override):
    """Settings in site.jsonc win over the preset. Empty strings/lists don't erase preset values."""
    if isinstance(base, dict) and isinstance(override, dict):
        out = dict(base)
        for k, v in override.items():
            out[k] = merge(base.get(k), v) if k in base else v
        return out
    if override in (None, "", []) and base not in (None, "", []):
        return base
    return override


def load_config(config_path=ROOT / "site.jsonc"):
    site = load_jsonc(config_path)
    name = site.get("preset") or "kids-club"
    preset_path = ROOT / "presets" / f"{name}.json"
    if not preset_path.exists():
        choices = ", ".join(sorted(p.stem for p in (ROOT / "presets").glob("*.json")))
        sys.exit(f'\nUnknown preset "{name}" in site.jsonc. Choose one of: {choices}\n')
    preset = json.loads(preset_path.read_text(encoding="utf-8"))
    return merge(preset, site)


# ---------------------------------------------------------------- helpers

esc = html.escape


def ext_link(url, label):
    return f'<a href="{esc(url)}" rel="noopener noreferrer">{esc(label)}</a>'


def hex_rgb(color):
    c = color.lstrip("#")
    if len(c) == 3:
        c = "".join(ch * 2 for ch in c)
    if not re.fullmatch(r"[0-9a-fA-F]{6}", c):
        sys.exit(f'\nTheme color "{color}" must be a hex color like "#1f4e79".\n')
    return tuple(int(c[i:i + 2], 16) for i in (0, 2, 4))


def luminance(rgb):
    def ch(v):
        v /= 255
        return v / 12.92 if v <= 0.03928 else ((v + 0.055) / 1.055) ** 2.4
    r, g, b = (ch(v) for v in rgb)
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def contrast(a, b):
    la, lb = luminance(hex_rgb(a)), luminance(hex_rgb(b))
    return (max(la, lb) + 0.05) / (min(la, lb) + 0.05)


def darken(color, f=0.75):
    return "#%02x%02x%02x" % tuple(int(v * f) for v in hex_rgb(color))


MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
DAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]


def fmt_date(d, style):
    if style == "intl":
        return f"{DAYS[d.weekday()]} {d.day} {MONTHS[d.month - 1]} {d.year}"
    return f"{DAYS[d.weekday()]}, {MONTHS[d.month - 1]} {d.day}, {d.year}"


def image_size(path):
    """Width/height of PNG, GIF, JPEG, or WebP files without any libraries."""
    data = path.read_bytes()
    if data[:8] == b"\x89PNG\r\n\x1a\n":
        return struct.unpack(">II", data[16:24])
    if data[:6] in (b"GIF87a", b"GIF89a"):
        return struct.unpack("<HH", data[6:10])
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        kind = data[12:16]
        if kind == b"VP8X":
            return (int.from_bytes(data[24:27], "little") + 1, int.from_bytes(data[27:30], "little") + 1)
        if kind == b"VP8 ":
            w, h = struct.unpack("<HH", data[26:30])
            return w & 0x3FFF, h & 0x3FFF
        if kind == b"VP8L":
            b = int.from_bytes(data[21:25], "little")
            return (b & 0x3FFF) + 1, ((b >> 14) & 0x3FFF) + 1
    if data[:2] == b"\xff\xd8":
        i = 2
        while i < len(data) - 9:
            if data[i] != 0xFF:
                i += 1
                continue
            marker = data[i + 1]
            if marker in (0xC0, 0xC1, 0xC2, 0xC3, 0xC5, 0xC6, 0xC7, 0xC9, 0xCA, 0xCB, 0xCD, 0xCE, 0xCF):
                h, w = struct.unpack(">HH", data[i + 5:i + 9])
                return w, h
            i += 2 + struct.unpack(">H", data[i + 2:i + 4])[0]
    return None


def png(width, height, pixel):
    """Tiny PNG writer: pixel(x, y) -> (r, g, b)."""
    rows = b"".join(b"\x00" + bytes(c for x in range(width) for c in pixel(x, y)) for y in range(height))
    def chunk(tag, body):
        return struct.pack(">I", len(body)) + tag + body + struct.pack(">I", zlib.crc32(tag + body) & 0xFFFFFFFF)
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(rows, 9)) + chunk(b"IEND", b""))


def badge_png(size_w, size_h, primary, accent):
    """A simple emblem image (accent ring on the primary color) for social previews and app icons."""
    p, a = hex_rgb(primary), hex_rgb(accent)
    cx, cy = size_w / 2, size_h / 2
    r_out = min(size_w, size_h) * 0.34
    r_in = r_out * 0.80
    stripe = size_h - max(6, size_h // 24)
    def pixel(x, y):
        if size_w > size_h and y >= stripe:
            return a
        d2 = (x - cx) ** 2 + (y - cy) ** 2
        return a if r_in * r_in <= d2 <= r_out * r_out else p
    return png(size_w, size_h, pixel)


# ---------------------------------------------------------------- page building

class Site:
    def __init__(self, cfg, base_url):
        self.cfg = cfg
        self.terms = cfg["terms"]
        self.group = cfg["group"]
        self.base_url = base_url                                   # "" when unknown
        self.base_path = urlparse(base_url).path or "/" if base_url else "/"
        self.theme = cfg["theme"]
        self.name = self.group["name"]
        self.today = dt.date.today()
        self.has_calendar = bool(cfg.get("calendar", {}).get("embed_url"))
        groups_label = self.terms.get("groups", "Groups")
        self.pages = [("index", "Home"), ("about", "About"), ("join", "Join"), ("groups", groups_label),
                      ("calendar", "Calendar"), ("gallery", "Gallery"), ("resources", "Resources"),
                      ("faq", "FAQ"), ("contact", "Contact")]
        self.footer_pages = self.pages + [("privacy", "Privacy & Safety")]

    # --- shared text
    def fill(self, text):
        c, g, m = self.cfg, self.group, self.cfg["meetings"]
        values = {"ages": c["program"]["ages"], "welcome": c["program"]["welcome"],
                  "meetings": m["summary"], "location": m["location"], "email": c["contact"]["email"],
                  "cost": c["cost"]["details"] or c["cost"]["summary"], "unit": self.terms["unit"],
                  "name": g["name"], "city": g["city"]}
        return re.sub(r"\{(\w+)\}", lambda mt: values.get(mt.group(1), mt.group(0)), text)

    def url(self, page):
        if not self.base_url:
            return ""
        return self.base_url if page == "index" else f"{self.base_url}{page}.html"

    def csp(self):
        frame = "https://calendar.google.com" if self.has_calendar else "'none'"
        return ("default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; "
                f"font-src 'self'; frame-src {frame}; connect-src 'self'; base-uri 'self'; "
                "form-action 'none'; object-src 'none'; upgrade-insecure-requests")

    def nav(self, current, pages, root):
        items = []
        for slug, label in pages:
            cur = ' aria-current="page"' if slug == current else ""
            items.append(f'<li><a href="{root}{slug}.html"{cur}>{esc(label)}</a></li>')
        return "\n        ".join(items)

    def email(self):
        return (self.cfg["contact"].get("email") or "").strip()

    def mail(self, subject="", text=None):
        """Email link, or "" when no email is set yet (so we never emit a bare mailto:)."""
        e = self.email()
        if not e:
            return ""
        q = f"?subject={subject}" if subject else ""
        return f'<a href="mailto:{esc(e)}{q}">{esc(text or e)}</a>'

    def footer(self, current, root):
        c = self.cfg
        bits = [self.mail()] if self.email() else []
        for key, prefix in (("charter", "Chartered by "), ("council", "")):
            org = c.get(key) or {}
            if org.get("name"):
                label = prefix + org["name"]
                bits.append(ext_link(org["url"], label) if org.get("url") else esc(label))
        socials = " &bull; ".join(ext_link(s["url"], s["name"]) for s in c["contact"].get("social", []) if s.get("url"))
        source = c["site"].get("source_url")
        source_html = (f'<p class="footer-source"><a href="{esc(source)}" rel="noopener noreferrer">'
                       f'Website source code</a></p>') if source else ""
        credit_html = ('<p class="footer-credit">Site template by Brandon Rogers &amp; '
                       '<a href="https://dmvthrowers.club/" rel="noopener noreferrer">DMV Throwers</a></p>'
                       ) if c["site"].get("credit", True) else ""
        return f"""<footer class="site-footer">
  <div class="wrap">
    <nav class="footer-nav" aria-label="Footer navigation">
      <ul>
        {self.nav(current, self.footer_pages, root)}
      </ul>
    </nav>
    <p>{" &bull; ".join(bits)}</p>
    {f'<p>{socials}</p>' if socials else ''}
    {source_html}
    <p class="footer-note">&copy; {self.today.year} {esc(self.name)}{(' &mdash; ' + esc(self.group['city'])) if self.group.get('city') else ''}</p>
    {credit_html}
  </div>
</footer>"""

    def layout(self, slug, title, description, body, jsonld=None, robots="index, follow"):
        root = self.base_path if slug == "404" else ""
        page_title = self.name if slug == "index" else f"{title} — {self.name}"
        head_urls = []
        if self.base_url:
            if slug != "404":
                head_urls.append(f'<link rel="canonical" href="{esc(self.url(slug))}">')
                head_urls.append(f'<meta property="og:url" content="{esc(self.url(slug))}">')
            head_urls.append(f'<meta property="og:image" content="{esc(self.base_url)}og-card.png">')
            head_urls.append('<meta property="og:image:width" content="1200">')
            head_urls.append('<meta property="og:image:height" content="630">')
        ld = []
        if self.base_url and slug not in ("index", "404"):
            ld.append({"@context": "https://schema.org", "@type": "BreadcrumbList", "itemListElement": [
                {"@type": "ListItem", "position": 1, "name": "Home", "item": self.url("index")},
                {"@type": "ListItem", "position": 2, "name": title, "item": self.url(slug)}]})
        if jsonld:
            ld.append(jsonld)
        ld_html = ""
        if ld:
            payload = json.dumps(ld if len(ld) > 1 else ld[0], indent=2, ensure_ascii=False).replace("</", "<\\/")
            ld_html = f'\n  <script type="application/ld+json">\n{payload}\n  </script>'
        tagline = self.group.get("tagline", "")
        sub = " — ".join(x for x in (tagline, self.place()) if x)
        page = f"""<!DOCTYPE html>
<html lang="{esc(self.cfg['site'].get('language') or 'en')}">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{esc(page_title)}</title>
  <meta name="description" content="{esc(description)}">
  <meta name="robots" content="{robots}">
  <meta name="referrer" content="strict-origin-when-cross-origin">
  <meta name="theme-color" content="{esc(self.theme['primary'])}">
  <meta http-equiv="Content-Security-Policy" content="{self.csp()}">
  {chr(10).join('  ' + h for h in head_urls).strip()}
  <meta property="og:type" content="website">
  <meta property="og:site_name" content="{esc(self.name)}">
  <meta property="og:title" content="{esc(page_title)}">
  <meta property="og:description" content="{esc(description)}">
  <meta name="twitter:card" content="summary_large_image">
  <link rel="icon" href="{root}favicon.svg" type="image/svg+xml">
  <link rel="apple-touch-icon" href="{root}apple-touch-icon.png">
  <link rel="manifest" href="{root}site.webmanifest">
  <link rel="stylesheet" href="{root}theme.css">
  <link rel="stylesheet" href="{root}style.css">{ld_html}
</head>
<body>
<a class="skip-link" href="#main-content">Skip to main content</a>
<header class="site-header">
  <div class="header-inner">
    <a class="brand" href="{root}index.html">
      <img class="brand-mark" src="{root}emblem.svg" alt="" width="44" height="44">
      <span class="brand-text"><span class="brand-name">{esc(self.name)}</span><span class="brand-sub">{esc(sub)}</span></span>
    </a>
    <button class="nav-toggle" type="button" aria-label="Menu" aria-expanded="false" aria-controls="site-nav">&#9776;</button>
  </div>
  <nav class="site-nav" id="site-nav" aria-label="Main navigation">
    <ul>
      {self.nav(slug, self.pages, root)}
    </ul>
  </nav>
</header>
<main id="main-content">
{body}{self.extra_content(slug)}
</main>
{self.footer(slug, root)}
<script src="{root}site.js" defer></script>
</body>
</html>
"""
        return re.sub(r"\n\s*\n(\s*<meta property=\"og:type\")", r"\n\1", page)

    def extra_content(self, slug):
        """Optional hand-written HTML in content/<page>.html, added at the end of that page."""
        f = ROOT / "content" / f"{slug}.html"
        if not f.exists():
            return ""
        return f'\n<section class="section section-extra">\n  <div class="wrap">\n{f.read_text(encoding="utf-8")}\n  </div>\n</section>'

    def place(self):
        return ", ".join(x for x in (self.group.get("city"), self.group.get("region")) if x)

    def page_head(self, title, lede):
        return f"""<section class="page-head">
  <div class="wrap">
    <h1>{esc(title)}</h1>
    <p>{esc(lede)}</p>
  </div>
</section>"""

    def cards(self, items, cls="cards"):
        return f'<div class="{cls}">' + "".join(
            f'\n  <div class="card"><h3>{esc(i["title"])}</h3><p>{esc(i["text"])}</p></div>' for i in items) + "\n</div>"

    def events(self, limit=None):
        upcoming, tbd = [], []
        for e in self.cfg.get("events", []):
            if not e.get("date"):
                tbd.append((None, e))
                continue
            try:
                d = dt.date.fromisoformat(e["date"])
            except ValueError:
                warnings.append(f'Event "{e.get("title")}" has a bad date "{e["date"]}" (use YYYY-MM-DD). Skipped.')
                continue
            if d >= self.today:
                upcoming.append((d, e))
        items = sorted(upcoming, key=lambda x: x[0]) + tbd
        return items[:limit] if limit else items

    def event_list(self, limit=None):
        items = self.events(limit)
        if not items:
            return '<p class="muted">No upcoming events posted yet. Check back soon!</p>'
        style = self.cfg["site"].get("date_format", "us")
        rows = []
        for d, e in items:
            when = fmt_date(d, style) if d else "Date to be announced"
            details = f'<p>{esc(e["details"])}</p>' if e.get("details") else ""
            rows.append(f'<li><span class="event-date">{esc(when)}</span><strong>{esc(e["title"])}</strong>{details}</li>')
        return '<ul class="event-list">\n' + "\n".join(rows) + "\n</ul>"

    # ------------------------------------------------------------ pages (one function each)

    def page_index(self):
        c, g, t = self.cfg, self.group, self.terms
        glance = [("When", c["meetings"]["summary"]), ("Where", c["meetings"]["location"]),
                  ("Cost", c["cost"]["summary"]), ("Contact", None)]
        glance_html = "".join(
            f'<div class="card glance"><span class="label">{esc(k)}</span>'
            + (f'<p class="value">{esc(v)}</p>' if v else
               f'<p class="value">{self.mail() or "<a href=" + chr(34) + "contact.html" + chr(34) + ">Contact page</a>"}</p>')
            + "</div>" for k, v in glance)
        body = f"""<section class="hero">
  <div class="wrap">
    <img class="hero-mark" src="emblem.svg" alt="{esc(self.name)} emblem" width="140" height="140">
    <h1>{esc(self.name)}</h1>
    <p class="tagline">{esc(g.get("tagline", ""))}</p>
    <p class="lede">{esc(g.get("description", ""))}</p>
    <div class="btn-row">
      <a class="btn btn-accent" href="join.html">Join the {esc(t["unit"])}</a>
      <a class="btn btn-ghost" href="contact.html">{esc(t.get("visit", "Visit a Meeting"))}</a>
    </div>
  </div>
</section>

<section class="section">
  <div class="wrap">
    <h2 class="center">What We're About</h2>
    {self.cards(c["program"]["pillars"], "cards cards-4")}
  </div>
</section>

<section class="section section-alt">
  <div class="wrap">
    <h2 class="center">At a Glance</h2>
    <div class="cards cards-4">{glance_html}</div>
  </div>
</section>

<section class="section">
  <div class="wrap narrow">
    <h2>Coming Up</h2>
    {self.event_list(limit=4)}
    <p><a href="calendar.html">See the full calendar</a></p>
  </div>
</section>"""
        org = {"@context": "https://schema.org", "@type": "Organization", "name": self.name,
               "description": g.get("description", ""), "email": c["contact"]["email"],
               "address": {"@type": "PostalAddress", "addressLocality": g.get("city", ""), "addressRegion": g.get("region", "")}}
        if self.base_url:
            org["url"] = self.base_url
            org["logo"] = self.base_url + "apple-touch-icon.png"
        if g.get("founded"):
            org["foundingDate"] = g["founded"]
        return "Home", g.get("description", ""), body, org

    def page_about(self):
        c, g, t = self.cfg, self.group, self.terms
        about = "".join(f"<p>{esc(self.fill(p))}</p>" for p in c["program"]["about"])
        facts = []
        if g.get("founded"):
            facts.append(f"Founded in {esc(g['founded'])}.")
        if g.get("serves"):
            facts.append(esc(g["serves"]))
        for key, label in (("charter", "Chartered by"), ("council", "Part of")):
            org = c.get(key) or {}
            if org.get("name"):
                facts.append(f"{label} {ext_link(org['url'], org['name']) if org.get('url') else esc(org['name'])}.")
        if c["program"].get("org_name"):
            facts.append(f"A member unit of {ext_link(c['program']['org_url'], c['program']['org_name'])}.")
        leaders = []
        for l in c.get("leaders", []):
            if l.get("open"):
                leaders.append(f'<li class="open-role"><span class="role">{esc(l["role"])}</span>'
                               f'<span class="who">Open — {self.mail("Volunteering", "volunteer with us") or "<a href=" + chr(34) + "contact.html" + chr(34) + ">volunteer with us</a>"}</span></li>')
            else:
                leaders.append(f'<li><span class="role">{esc(l["role"])}</span><span class="who">{esc(l.get("name", ""))}</span></li>')
        leaders_html = (f'<h2>Our {esc(t.get("leaders", "Leaders"))}</h2>\n    <ul class="leader-list">{"".join(leaders)}</ul>'
                        if leaders else "")
        body = f"""{self.page_head(f"About the {t['unit']}", g.get("description", ""))}

<section class="section">
  <div class="wrap narrow">
    <h2>{esc(c["program"]["about_title"])}</h2>
    {about}
  </div>
</section>

<section class="section section-alt">
  <div class="wrap narrow">
    <h2>Our {esc(t["unit"])}</h2>
    <p>{" ".join(facts) or esc(g.get("description", ""))}</p>
    {leaders_html}
  </div>
</section>

<section class="section">
  <div class="wrap narrow">
    <h2>{esc(c["safety"]["title"])}</h2>
    <ul class="checklist">{"".join(f"<li>{esc(p)}</li>" for p in c["safety"]["points"])}</ul>
    <p><a href="privacy.html">Our privacy and photo policy</a></p>
  </div>
</section>"""
        return "About", f"About {self.name}: who we are, what we do, and who leads us.", body, None

    def page_join(self):
        c, t = self.cfg, self.terms
        steps = "".join(f'\n  <li class="step"><h3>{esc(s["title"])}</h3><p>{esc(self.fill(s["text"]))}</p></li>'
                        for s in c["join_steps"])
        jl = c.get("join_link") or {}
        join_btn = (f'<p class="center"><a class="btn btn-primary" href="{esc(jl["url"])}" rel="noopener noreferrer">{esc(jl["label"])}</a></p>'
                    if jl.get("url") and jl.get("label") else "")
        aid = c["cost"].get("aid_url")
        aid_html = f' {ext_link(aid, "Financial help is available.")}' if aid else ""
        serves = f' {esc(self.group["serves"])}' if self.group.get("serves") else ""
        body = f"""{self.page_head(f"Join the {t['unit']}", f"Open to kids {c['program']['ages']}. {c['program']['welcome']}.")}

<section class="section">
  <div class="wrap">
    <h2 class="center">How to Join</h2>
    <ol class="steps">{steps}
    </ol>
    {join_btn}
  </div>
</section>

<section class="section section-alt">
  <div class="wrap">
    <div class="cards cards-3">
      <div class="card"><h3>Who Can Join</h3><p>Kids {esc(c["program"]["ages"])}. {esc(c["program"]["welcome"])}.{serves}</p></div>
      <div class="card"><h3>Cost</h3><p>{esc(c["cost"]["details"] or c["cost"]["summary"])}{aid_html}</p></div>
      <div class="card"><h3>What to Wear</h3><p>{esc(c["uniform"])}</p></div>
    </div>
    <p class="center"><a class="btn btn-primary" href="contact.html">Questions? Contact Us</a></p>
  </div>
</section>"""
        return "Join", f"How to join {self.name}: who can join, steps, cost, and what to wear.", body, None

    def page_groups(self):
        c, t = self.cfg, self.terms
        cards = "".join(f'\n  <div class="card"><span class="label">{esc(gp.get("ages", ""))}</span>'
                        f'<h3>{esc(gp["name"])}</h3><p>{esc(gp["text"])}</p></div>' for gp in c["groups"])
        body = f"""{self.page_head(f"Our {t['groups']}", c.get("groups_intro", ""))}

<section class="section">
  <div class="wrap">
    <div class="cards cards-3">{cards}
    </div>
  </div>
</section>"""
        names = ", ".join(gp["name"] for gp in c["groups"])
        return t["groups"], f"{self.name} {t['groups'].lower()}: {names}.", body, None

    def page_calendar(self):
        c = self.cfg
        embed = c.get("calendar", {}).get("embed_url", "")
        frame = ""
        if embed:
            if not embed.startswith("https://calendar.google.com/"):
                warnings.append("calendar.embed_url should start with https://calendar.google.com/ (ignored).")
            else:
                frame = (f'<iframe class="cal-frame" title="{esc(self.name)} calendar" src="{esc(embed)}" loading="lazy"></iframe>\n'
                         f'    <p class="muted center">Calendar not loading? '
                         + (f'Email {self.mail()} for dates.' if self.email() else 'Ask a leader at a meeting for dates.') + '</p>')
        season = f' We meet {esc(c["meetings"]["season"])}.' if c["meetings"].get("season") else ""
        mtgs = self.terms.get("meetings", "meetings")
        body = f"""{self.page_head("Calendar", f"{mtgs.capitalize()}, events, and activities.")}

<section class="section">
  <div class="wrap narrow">
    <h2>{esc(self.terms.get("meetings_title", "Regular Meetings"))}</h2>
    <p><strong>{esc(c["meetings"]["summary"])}</strong> at {esc(c["meetings"]["location"])}.{season}</p>
    <h2>Upcoming Events</h2>
    {self.event_list()}
    {frame}
  </div>
</section>"""
        return "Calendar", f"{self.name} calendar: {mtgs} and upcoming events.", body, None

    def page_gallery(self):
        c = self.cfg
        figs = []
        photos = c.get("photos") or {}
        listed = c.get("gallery", [])
        if listed and photos.get("permission_confirmed") is not True:
            warnings.append(f'Your gallery lists {len(listed)} photo(s), but none are shown: set photos.permission_confirmed '
                            'to true in site.jsonc once you have written permission from a parent or guardian for every child in them.')
            listed = []
        for ph in listed:
            src = ROOT / "assets" / ph["src"]
            if not src.exists():
                warnings.append(f'Gallery photo not found: assets/{ph["src"]}')
                continue
            size = image_size(src)
            if not size:
                warnings.append(f'Could not read the size of {ph["src"]}; use a JPG, PNG, GIF, or WebP file.')
                continue
            if src.stat().st_size > 500_000:
                warnings.append(f'{ph["src"]} is {src.stat().st_size // 1024} KB; resize it under 500 KB so pages load fast.')
            if not ph.get("alt"):
                warnings.append(f'{ph["src"]} has no "alt" description; screen-reader users need one.')
            cap = f'<figcaption>{esc(ph["caption"])}</figcaption>' if ph.get("caption") else ""
            figs.append(f'<figure><img src="{esc(ph["src"])}" alt="{esc(ph.get("alt", ""))}" width="{size[0]}" '
                        f'height="{size[1]}" loading="lazy" decoding="async">{cap}</figure>')
        grid = (f'<div class="gallery-grid">\n' + "\n".join(figs) + "\n</div>") if figs else \
            '<p class="muted center">Photos coming soon.</p>'
        mtgs = self.terms.get("meetings", "meetings")
        body = f"""{self.page_head("Gallery", f"{mtgs.capitalize()}, events, and adventures.")}

<section class="section">
  <div class="wrap">
    {grid}
    <p class="muted center">Have photos to share? {("Send them to " + self.mail() + ".") if self.email() else "Give them to a leader at a meeting."} We only post photos of kids with a parent's written permission.</p>
  </div>
</section>"""
        return "Gallery", f"Photos from {self.name} {mtgs} and events.", body, None

    def page_resources(self):
        c = self.cfg
        items = list(c.get("resources", [])) + list(c.get("links", []))
        if c["safety"].get("training_url"):
            items.append({"title": c["safety"]["training_name"], "text": "Training and safety resources for adult volunteers.",
                          "url": c["safety"]["training_url"], "label": "Learn more"})
        for key, title in (("council", "Our Council"), ("charter", "Our Chartered Organization")):
            org = c.get(key) or {}
            if org.get("name") and org.get("url"):
                items.append({"title": title, "text": org["name"], "url": org["url"], "label": "Visit website"})
        # A thank-you to DMV Throwers, the club that made this template. Delete these two lines to remove it.
        items.append({"title": "Learn to Yo-Yo", "text": "A free how-to guide from DMV Throwers, the yo-yo club behind this template.",
                      "url": "https://dmvthrowers.club/learn-yoyo.html", "label": "dmvthrowers.club"})
        cards = "".join(f'\n  <div class="card"><h3>{esc(i["title"])}</h3><p>{esc(i.get("text", ""))}</p>'
                        f'<p>{ext_link(i["url"], i.get("label") or i["url"])}</p></div>' for i in items if i.get("url"))
        if not cards:
            cards = '\n  <div class="card"><h3>Questions?</h3><p>Answers to common questions.</p><p><a href="faq.html">Read the FAQ</a></p></div>'
        body = f"""{self.page_head("Resources", "Helpful links for families.")}

<section class="section">
  <div class="wrap">
    <div class="cards cards-3">{cards}
    </div>
  </div>
</section>"""
        return "Resources", f"Helpful links for {self.name} families.", body, None

    def page_faq(self):
        c = self.cfg
        qa = [(self.fill(f["q"]), self.fill(f["a"])) for f in list(c.get("faq", [])) + list(c.get("faq_extra", []))]
        items = "".join(f'\n  <details class="faq-item"><summary>{esc(q)}</summary><p>{esc(a)}</p></details>' for q, a in qa)
        ld = {"@context": "https://schema.org", "@type": "FAQPage", "mainEntity": [
            {"@type": "Question", "name": q, "acceptedAnswer": {"@type": "Answer", "text": a}} for q, a in qa]}
        body = f"""{self.page_head("Frequently Asked Questions", "What new families ask most. Don't see yours? Email us.")}

<section class="section">
  <div class="wrap narrow">
    <div class="faq-list">{items}
    </div>
  </div>
</section>"""
        return "FAQ", f"{self.name} FAQ: who can join, {self.terms.get('meetings', 'meetings')}, cost, and more.", body, ld

    def page_contact(self):
        c = self.cfg
        phone = c["contact"].get("phone")
        phone_html = f'<p>Phone: <a href="tel:{esc(re.sub(r"[^0-9+]", "", phone))}">{esc(phone)}</a></p>' if phone else ""
        socials = "".join(f"<li>{ext_link(s['url'], s['name'])}</li>" for s in c["contact"].get("social", []) if s.get("url"))
        social_html = f'<ul class="inline-list">{socials}</ul>' if socials else ""
        mtgs = self.terms.get("meetings", "meetings")
        body = f"""{self.page_head("Contact Us", f"Questions about joining, {mtgs}, or volunteering? We'd love to hear from you.")}

<section class="section">
  <div class="wrap narrow">
    <div class="card contact-card">
      <h2>Get in Touch</h2>
      {('<p class="big-email">' + self.mail() + '</p>') if self.email() else '<p>Our troop email address is coming soon. Come to a meeting or check back here.</p>'}
      {phone_html}
      <p><strong>{esc(mtgs.capitalize())}:</strong> {esc(c["meetings"]["summary"])}<br>{esc(c["meetings"]["location"])}</p>
      <p>{"Just show up, or email first and we'll watch for you." if self.email() else "Just show up. We'll watch for you."}</p>
      {social_html}
    </div>
  </div>
</section>"""
        return "Contact", f"Contact {self.name}: email, {self.terms.get('meeting', 'meeting')} time, and place.", body, None

    def page_privacy(self):
        c = self.cfg
        cal = (" The Calendar page shows a Google Calendar, covered by the "
               + ext_link("https://policies.google.com/privacy", "Google Privacy Policy") + ".") if self.has_calendar else ""
        body = f"""{self.page_head("Privacy & Safety", "How this website handles information, and how we keep kids safe.")}

<section class="section">
  <div class="wrap narrow prose">
    <h2>What This Website Collects</h2>
    <p>Nothing. This site has no sign-up forms, cookies, analytics, ads, or tracking. It is hosted on
      GitHub Pages, which may log basic technical data for security under the
      {ext_link("https://docs.github.com/en/site-policy/privacy-policies/github-general-privacy-statement", "GitHub Privacy Statement")}.{cal}</p>
    <h2>When You Email Us</h2>
    <p>We use your name, email, and anything you share only to answer you and run our activities. We never sell or share it.</p>
    <h2>{esc(c["safety"]["title"])}</h2>
    <ul>{"".join(f"<li>{esc(p)}</li>" for p in c["safety"]["points"])}</ul>
    <h2>Photo Removal</h2>
    <p>Want a photo taken down? {("Email " + self.mail()) if self.email() else "Tell a leader at a meeting"} and we'll remove it promptly.</p>
  </div>
</section>"""
        return "Privacy & Safety", f"How {self.name} handles your information and keeps kids safe.", body, None

    def page_404(self):
        root = self.base_path
        body = f"""{self.page_head("Page Not Found", "That page doesn't exist. It may have moved.")}

<section class="section">
  <div class="wrap center">
    <p class="btn-row"><a class="btn btn-primary" href="{root}index.html">Go to Home</a>
      <a class="btn btn-primary" href="{root}calendar.html">See the Calendar</a></p>
  </div>
</section>"""
        return "Page Not Found", f"Page not found — {self.name}.", body, None

    # ------------------------------------------------------------ generated files

    def theme_css(self):
        t = self.theme
        on_accent = "#111111" if contrast(t["accent"], "#111111") >= contrast(t["accent"], "#ffffff") else "#ffffff"
        checks = [("white text on your primary color", "#ffffff", t["primary"]),
                  ("text on your background color", t["ink"], t["background"]),
                  ("headings (primary color) on your background color", t["primary"], t["background"])]
        for what, fg, bg in checks:
            ratio = contrast(fg, bg)
            if ratio < 4.5:
                warnings.append(f"Hard to read: {what} has contrast {ratio:.1f}:1 (needs 4.5:1). Try a darker or lighter color.")
        return f"""/* Generated by build.py from your theme colors. Edit colors in site.jsonc, not here. */
:root {{
  --primary: {t["primary"]};
  --primary-dark: {darken(t["primary"])};
  --accent: {t["accent"]};
  --on-accent: {on_accent};
  --bg: {t["background"]};
  --ink: {t["ink"]};
}}
"""

    def emblem_svg(self):
        t = self.theme
        label = (self.group.get("number") or "".join(w[0] for w in re.findall(r"[A-Za-z0-9]+", self.name))[:3]).upper()[:4]
        size = {1: 46, 2: 36, 3: 26, 4: 20}.get(len(label), 20)
        return f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100" width="100" height="100" role="img" aria-label="{esc(self.name)}">
  <circle cx="50" cy="50" r="48" fill="{t["accent"]}"/>
  <circle cx="50" cy="50" r="41" fill="{t["primary"]}"/>
  <circle cx="50" cy="50" r="35" fill="none" stroke="{t["accent"]}" stroke-width="1.5" stroke-dasharray="3 3"/>
  <text x="50" y="50" text-anchor="middle" dominant-baseline="central" font-family="system-ui, -apple-system, 'Segoe UI', Roboto, sans-serif" font-weight="800" font-size="{size}" fill="#ffffff">{esc(label)}</text>
</svg>
"""

    def build(self):
        if OUT.exists():
            shutil.rmtree(OUT)
        shutil.copytree(ROOT / "assets", OUT)
        (OUT / ".nojekyll").write_text("")
        (OUT / "theme.css").write_text(self.theme_css())
        if not (OUT / "emblem.svg").exists():                       # your own assets/emblem.svg wins
            (OUT / "emblem.svg").write_text(self.emblem_svg())
        if not (OUT / "favicon.svg").exists():
            shutil.copy(OUT / "emblem.svg", OUT / "favicon.svg")
        if not (OUT / "og-card.png").exists():                     # your own assets/og-card.png wins
            (OUT / "og-card.png").write_bytes(badge_png(1200, 630, self.theme["primary"], self.theme["accent"]))
        if not (OUT / "apple-touch-icon.png").exists():
            (OUT / "apple-touch-icon.png").write_bytes(badge_png(180, 180, self.theme["primary"], self.theme["accent"]))
        (OUT / "site.webmanifest").write_text(json.dumps({
            "name": self.name, "short_name": (self.group.get("number") and f'{self.terms["unit"]} {self.group["number"]}') or self.name[:24],
            "start_url": "./", "display": "browser", "background_color": self.theme["background"],
            "theme_color": self.theme["primary"],
            "icons": [{"src": "apple-touch-icon.png", "sizes": "180x180", "type": "image/png"},
                      {"src": "emblem.svg", "sizes": "any", "type": "image/svg+xml"}]}, indent=2))
        for slug, _ in self.footer_pages + [("404", "")]:
            title, desc, body, ld = getattr(self, f"page_{slug}")()
            robots = "noindex, follow" if slug == "404" or getattr(self, "noindex", False) else "index, follow"
            (OUT / f"{slug}.html").write_text(self.layout(slug, title, desc, body, ld, robots), encoding="utf-8")
        robots = "User-agent: *\nAllow: /\n"
        if self.base_url:
            robots += f"\nSitemap: {self.base_url}sitemap.xml\n"
            urls = "".join(f"  <url><loc>{esc(self.url(s))}</loc><lastmod>{self.today.isoformat()}</lastmod></url>\n"
                           for s, _ in self.footer_pages)
            (OUT / "sitemap.xml").write_text('<?xml version="1.0" encoding="UTF-8"?>\n'
                                             '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n' + urls + "</urlset>\n")
        else:
            warnings.append("No site URL set, so canonical links, social previews, and sitemap.xml were skipped. "
                            "(Automatic on GitHub Pages; or set site.url in site.jsonc.)")
        (OUT / "robots.txt").write_text(robots)
        # The base path lets scripts/check_site.py resolve 404.html's absolute links.
        if OUT == ROOT / "_site":
            (ROOT / ".build-base-path").write_text(self.base_path)
            photos = self.cfg.get("photos") or {}
            (ROOT / ".build-privacy.json").write_text(json.dumps({
                "first_names_only": photos.get("first_names_only") is not False,
                "allowed_names": [n for n in photos.get("allowed_names", []) if isinstance(n, str)]}))


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--base-url", default=os.environ.get("SITE_URL", ""), help="public address, e.g. https://example.org/")
    ap.add_argument("--serve", action="store_true", help="preview at http://localhost:8000/ after building")
    ap.add_argument("--config", default="site.jsonc", help="settings file (default: site.jsonc)")
    ap.add_argument("--out", default="_site", help="output folder (default: _site)")
    ap.add_argument("--noindex", action="store_true", help="ask search engines not to list the site (demos)")
    args = ap.parse_args()
    global OUT
    OUT = (ROOT / args.out).resolve()
    cfg = load_config((ROOT / args.config).resolve())
    # Vercel always sets VERCEL_PROJECT_PRODUCTION_URL (host name only), so no setup is needed there.
    vercel_host = os.environ.get("VERCEL_PROJECT_PRODUCTION_URL", "").strip()
    base_url = (args.base_url or cfg["site"].get("url") or (vercel_host and f"https://{vercel_host}/") or "").strip()
    if base_url and not base_url.endswith("/"):
        base_url += "/"
    if base_url.startswith("http://"):
        # GitHub Pages reports http:// until "Enforce HTTPS" is on; the site is still served over HTTPS.
        base_url = "https://" + base_url[len("http://"):]
        warnings.append(f"Using {base_url} (https). On GitHub Pages, tick Settings > Pages > Enforce HTTPS.")
    if base_url and urlparse(base_url).scheme != "https":
        warnings.append(f"Site URL {base_url} should start with https://")
    site = Site(cfg, base_url)
    site.noindex = args.noindex
    site.build()
    print(f"Built {cfg.get('preset_name', cfg.get('preset'))} site for {site.name} into {OUT.relative_to(ROOT)}/"
          + (f" (address: {base_url})" if base_url else ""))
    for w in dict.fromkeys(warnings):          # each warning once, in order
        print("  WARNING:", w)
    if args.serve:
        os.chdir(OUT)
        print("Preview: http://localhost:8000/   (Ctrl+C to stop)")
        http.server.ThreadingHTTPServer(("127.0.0.1", 8000), http.server.SimpleHTTPRequestHandler).serve_forever()


if __name__ == "__main__":
    main()
