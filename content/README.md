# Extra page content (optional)

Put an HTML file here named after a page, and the build adds it as a new section at the bottom of
that page:

| File | Added to |
| --- | --- |
| `index.html` | Home |
| `about.html` | About |
| `join.html` | Join |
| `groups.html` | Groups (Dens / Patrols / Levels) |
| `calendar.html` | Calendar |
| `gallery.html` | Gallery |
| `resources.html` | Resources |
| `faq.html` | FAQ |
| `contact.html` | Contact |
| `privacy.html` | Privacy & Safety |

Example `content/about.html`:

```html
<h2>Our History</h2>
<p>We started in 2026 with six kids and two parents in a library meeting room.
  Today we're 30 members strong.</p>
<ul>
  <li>2026: First campout</li>
  <li>2027: Food drive collected 500 cans</li>
</ul>
```

Use plain HTML. No `<script>`, `<style>`, or `style="…"` attributes; the site's security policy
blocks them, and the automatic check will fail. Add CSS to `assets/style.css` instead. This
README itself is ignored by the build.
