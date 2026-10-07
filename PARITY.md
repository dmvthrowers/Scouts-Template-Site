# Parity: live sites and this template

Two live sites are built from this template. They stay in step with it, so the template is always
what real troops and packs actually run.

| Live site | Repo | How it's built |
|---|---|---|
| Girl Scout Troop 80301 | [`Girl-Scout-Troop-80301`](https://github.com/dmvthrowers/Girl-Scout-Troop-80301) | From this template: `site.jsonc` + `build.py` |
| Cub Scout Pack 1125 | [`pack1125-dumfries`](https://github.com/dmvthrowers/pack1125-dumfries) | Hand-written HTML in `docs/`, from the same design |

For the troop site, parity means the same `build.py`, `scripts/check_site.py` and `assets/` as here,
with only `site.jsonc` and `content/` being its own. For the pack site, parity means the same pages,
sections, features and fixes, not the same files.

## The rule

Every PR to this template or to a live site does one of three things, and says which in its
description:

1. **Ports the change** to the other repos (link the matching PRs).
2. **Logs it below** as a known gap, with the reason.
3. **Says it's site-only** because it's that unit's own settings or content (names, meeting times,
   events, photos). Settings and content never come back here; code and fixes always do.

A fix usually starts in a live site, because that's where it was found. It is ported here, or logged,
before the PR merges.

## Known gaps

Audited 2026-10-07. Remove a row when it's closed.

### Girl Scout Troop 80301 (behind the template)

The troop's `build.py` is an older copy. Every difference is a template improvement the troop
doesn't have yet, so the fix is to copy the template's `build.py` into the troop repo, then
rebuild and run the check.

| Gap | Note |
|---|---|
| Custom words (`terms`): "Visit a Meeting", "Leaders", "meetings", "Regular Meetings" | Hard-coded in the troop copy; configurable in the template |
| Automatic site address on Vercel (`VERCEL_PROJECT_PRODUCTION_URL`) | Missing from the troop copy |
| "Learn to Yo-Yo" resource credit | In the template; the troop can keep or delete it after the copy |
| Sports presets (soccer, baseball, basketball, football, sports club) | Not in the troop copy; harmless, but copy `presets/` too so a later update is one step |
| `DEPLOY.md` and `TEMPLATE-README.md` | Only in the troop repo. Decide whether they're troop-only or belong in the template |

### Cub Scout Pack 1125 (hand-written)

| Gap | Note |
|---|---|
| Loads Google Fonts on every page | The template promises no outside fonts. Self-host the fonts or use the system stack, and drop `fonts.googleapis.com` and `fonts.gstatic.com` from the CSP |
| Official rank badge images (`badge-*.png`) on the dens page | The template asks for official insignia only when the unit supplies them and confirms it may use them. Confirm, or swap for plain rank names |
| `scripts/check_site.py` differs from the template's | Bring the pack's check in line so both catch the same problems |
| A "Dens" page where the template has "Groups" | Same idea; fine as is. Port any feature the pack's page has that the template's lacks |
| Youth Protection section on the Join page (template build plan 1.16) | The pack mentions Youth Protection on its resources and privacy pages but not on its join page. Add a short section there with the two-adult line and the official training link |
| Same pages otherwise (home, about, join, calendar, gallery, resources, FAQ, contact, privacy, 404) | No gap |

This file, like `showcase/` and `examples/`, only applies to the original template repository. Delete
it in your own copy.
