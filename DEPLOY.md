# Site maintenance notes

Keep this file in your copy of the template and fill it in. It's the page you hand to the next
leader, so they know where the site lives, what's done, and what's still open. Delete the lines in
[brackets] as you replace them. The template's own README has the full instructions; this file is
only your group's checklist.

The site builds with GitHub Actions and publishes to **[your site address]**.
Edit it in `site.jsonc` (see the README, "What to change").

## Who looks after it

- **Site owner:** [name and role]. They can change settings on GitHub.
- **Backup person:** [name and role]. Make sure at least two people have access to the repository, the
  domain account (if you have a domain) and the shared email inbox.
- **Shared email:** [address]. Use a group address, never a personal one.

## What's filled in

[One line per thing that is done, for example: name and number, meeting day and place, leaders who
agreed to be listed, the first events, the colors.]

## Still to do (also marked in `site.jsonc`)

- [ ] **Shared email:** set `contact.email` to a group address. Until it's set, the site points visitors to the contact page.
- [ ] **Meeting time and place:** update `meetings` once decided. Keep the place general (building and town).
- [ ] **Leaders:** list a person only after they say yes. The site is public and kids use it.
- [ ] **Cost:** say what dues are in `cost`, or "to be announced".
- [ ] **Photos:** only with written parent or guardian permission, and no full names of kids. Then set `photos.permission_confirmed` in `site.jsonc`.
- [ ] **Events:** add the next few as `YYYY-MM-DD`. Past ones hide themselves.
- [ ] **Own domain (optional):** the free GitHub address works. If you want something like `troop123.org`,
      follow the README's "Custom domain" section. Check the renewal price, turn on WHOIS privacy, and
      ask your council before putting its name or trademark in the address.

## When something goes wrong

- **A red X on the Actions tab:** click the run. The message says what to fix (a typo in `site.jsonc`, a
  missing photo). The live site stays as it was until it's fixed.
- **The very first run failed:** turn on **Settings → Pages → Source: GitHub Actions**, then **Actions →
  Build and deploy → Run workflow**.
- **Someone asks for a photo or name to come down:** remove it the same day and commit.

## Handing it over

When the site owner changes, add the new person as a collaborator, move the domain and email to them,
and update the names above.
