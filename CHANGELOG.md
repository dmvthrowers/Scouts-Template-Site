# Changelog

What changed in each release of this template. Newest first. Copies of the template can use it to see what is new before they update (see [docs/UPDATING.md](docs/UPDATING.md)).

## Unreleased

Changes that merge after 1.0.0 are listed here until the next tag.

- Search and AI findability: every page title and description now names the town ("About — Troop 123, Springfield VA"), so local searches match. The home page's Organization data drops an empty email and adds the area served, the council as parent organization, and social links. The build also writes `llms.txt`, a plain-text summary of the group and its pages for AI assistants.

## 1.0.0

The first tagged release: a youth group website built from one settings file.

- Ten pages from `site.jsonc` and a preset: home, about, join, groups, calendar, gallery, resources, FAQ, contact and privacy, plus a 404.
- Presets for Cub Scouts, Scouts BSA, Girl Scouts, a kids club and five youth sports (soccer, baseball, football, basketball, other).
- Hosting guides for GitHub Pages, Cloudflare Pages and Vercel, and a custom-domain guide.
- Kids' privacy built in: no full names, photo rules, no cookies or trackers, strict security policy.
- `scripts/check_site.py` checks links, alt text, headers and footers, and the security policy.
- The build never emits an empty email link; Escape closes the phone menu and returns focus to its button.
- A "Learn to Yo-Yo" thank-you link on the Resources page (delete it to remove it).

