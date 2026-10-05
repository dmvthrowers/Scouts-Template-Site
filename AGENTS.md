# Instructions for AI coding agents

You're helping someone launch a website for a Scout unit, Girl Scout troop, or kids club from this
template. The human-facing guide is [README.md](README.md). Read it, then follow this.

## Goal
Get a correct, live site in one session (15–30 minutes) with as few human steps as possible.

## Steps
1. **Collect facts from the user**:
   - preset (`kids-club`, `cub-scouts`, `scouts-bsa`, `girl-scouts`)
   - group name and number
   - town and region
   - meeting days, time, and place
   - a shared contact email
   - cost
   - leaders (with their consent)
   - upcoming events
   - optional: brand colors and a public Google Calendar embed URL

   Never invent facts. Leave a value empty (`""`), or use "to be announced", rather than guess.
2. **Edit `site.jsonc` only** for content. Keep `//` comments on their own lines. Change preset
   wording by adding the same key to `site.jsonc`, not by editing the preset.
3. **Build and check locally:** `python3 build.py && python3 scripts/check_site.py`. Fix every
   WARNING the build prints (contrast, missing photos, bad dates) and every check failure.
4. **Deploy (GitHub Pages):** the human must:
   - create the repository from the template ("Use this template")
   - set **Settings → Pages → Source: GitHub Actions**

   Then push to `main`. The workflow builds, checks, and deploys. Confirm the run is green and the
   page URL loads (HTTP 200, the group name in `<title>`).
5. **Report** the live URL and anything the user still needs to do. Typical items: making the
   Google Calendar public, adding a custom domain, turning on two-factor login.

## Rules
- **Kids' privacy:**
  - No full names of children anywhere.
  - Photos only with the user's confirmation of written parent/guardian permission.
  - Resize photos to ~1200px and under 500 KB, and strip EXIF/GPS metadata.
  - Never publish a personal home address. Avoid personal phone numbers unless the person explicitly agrees.
- **Security:**
  - No inline `<script>`, `<style>`, `style=""`, or `on*=` handlers. The CSP blocks them and the check fails.
  - No `http://` links.
  - No trackers, analytics, or third-party scripts unless the user asks. If they do, update the
    CSP in `Site.csp()` in `build.py` and the Privacy page text.
- **Trademarks:** don't add official logos, badges, or insignia of Scouting America or Girl Scouts
  of the USA unless the user supplies them and confirms they may use them.
- **Consistency:** every page shares one header and footer (built by `Site.layout` and
  `Site.footer`). The check fails if they differ.
- **Pages:** each page is one `page_<slug>()` method in `build.py`. To add a page, add a method
  and an entry in `self.pages`.
- **Extra content:** `content/<slug>.html` is appended to that page. Plain HTML only.
- **No dependencies:** keep `build.py` and `scripts/check_site.py` standard-library Python 3.9+.

## Useful commands
```sh
python3 build.py --serve                     # build + preview at http://localhost:8000/
python3 build.py --base-url https://x.org/   # build for a specific address (canonical URLs, sitemap)
python3 scripts/check_site.py                # must print "OK"
```
