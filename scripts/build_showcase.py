#!/usr/bin/env python3
"""Build this template's own showcase site into _site/: the "how to deploy" guide page
(showcase/index.html) plus live example sites in _site/examples/<name>/.

Used only by the original template repository (see .github/workflows/deploy.yml).
Copies of the template build their own site with build.py instead.
"""
import os
import shutil
import subprocess
import sys
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "_site"
EXAMPLES = [                               # (folder name, settings file)
    ("pack-1125", "examples/pack-1125.jsonc"),
    ("demo-kids-club", "site.jsonc"),
    ("demo-scouts-bsa", "examples/demo-scouts-bsa.jsonc"),
    ("demo-girl-scouts", "examples/demo-girl-scouts.jsonc"),
    ("demo-soccer", "examples/demo-soccer.jsonc"),
]

base_url = os.environ.get("SITE_URL", "").strip()
if base_url.startswith("http://"):          # GitHub Pages reports http:// until HTTPS is enforced
    base_url = "https://" + base_url[len("http://"):]
if base_url and not base_url.endswith("/"):
    base_url += "/"

if OUT.exists():
    shutil.rmtree(OUT)
shutil.copytree(ROOT / "showcase", OUT)
(OUT / ".nojekyll").write_text("")
robots = "User-agent: *\nAllow: /\n"
if base_url:
    robots += f"\nSitemap: {base_url}sitemap.xml\n"
    (OUT / "sitemap.xml").write_text('<?xml version="1.0" encoding="UTF-8"?>\n'
                                     '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
                                     f"  <url><loc>{base_url}</loc></url>\n</urlset>\n")
(OUT / "robots.txt").write_text(robots)

# GitHub Pages serves the root 404.html for any missing page, at any depth, so its links are
# absolute to the site's base path. Without it, visitors get GitHub's generic error page.
root = urlparse(base_url).path if base_url else "/"
(OUT / "404.html").write_text(f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Page Not Found — Youth Group Site Template</title>
  <meta name="description" content="That page doesn't exist. See the free website template for Scout units and kids clubs.">
  <meta name="robots" content="noindex, follow">
  <meta name="referrer" content="strict-origin-when-cross-origin">
  <meta name="theme-color" content="#0b3d6e">
  <meta http-equiv="Content-Security-Policy" content="default-src 'self'; script-src 'none'; style-src 'self'; img-src 'self'; font-src 'self'; frame-src 'none'; connect-src 'none'; base-uri 'self'; form-action 'none'; object-src 'none'; upgrade-insecure-requests">
  <link rel="icon" href="{root}favicon.svg" type="image/svg+xml">
  <link rel="stylesheet" href="{root}showcase.css">
</head>
<body>
<a class="skip-link" href="#main-content">Skip to main content</a>
<header class="top">
  <div class="wrap top-inner">
    <a class="brand" href="{root}"><img src="{root}favicon.svg" alt="" width="36" height="36"><span>Youth Group Site Template</span></a>
  </div>
</header>
<main id="main-content">
<section class="hero">
  <div class="wrap">
    <h1>Page Not Found</h1>
    <p class="lede">That page doesn't exist. It may have moved, or the example site it belonged to was renamed.</p>
    <p><a class="btn btn-accent" href="{root}">See the template and live examples</a></p>
  </div>
</section>
</main>
</body>
</html>
""", encoding="utf-8")

for name, config in EXAMPLES:
    url = f"{base_url}examples/{name}/" if base_url else ""
    out = f"_site/examples/{name}"
    subprocess.run([sys.executable, "build.py", "--config", config, "--out", out, "--base-url", url, "--noindex"],
                   cwd=ROOT, check=True)
    base_path = urlparse(url).path if url else "/"
    subprocess.run([sys.executable, "scripts/check_site.py", out, base_path], cwd=ROOT, check=True)

print(f"Showcase built into _site/ with {len(EXAMPLES)} examples" + (f" at {base_url}" if base_url else ""))
