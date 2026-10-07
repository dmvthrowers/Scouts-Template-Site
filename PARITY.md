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

Checked 2026-10-07. Remove a row when it's closed.

| Gap | Where | Note |
|---|---|---|
| Troop `build.py` differs from the template's (32 changed lines) | `Girl-Scout-Troop-80301` | Not synced back yet. Decide line by line: generic fixes come here, troop settings move to `site.jsonc` |
| Troop has `DEPLOY.md` and `TEMPLATE-README.md` that the template doesn't | `Girl-Scout-Troop-80301` | Decide whether they're troop-only or belong here |
| Pack site vs. the template's pages and features | `pack1125-dumfries` | Not audited yet; do a first pass and fill in this row |

This file, like `showcase/` and `examples/`, only applies to the original template repository. Delete
it in your own copy.
