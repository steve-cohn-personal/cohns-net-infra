# Handoff bundle — home page and /foodie

Design source: `Home A Columns.dc.html`, `Foodie Hub.dc.html` (Claude Design project "Steve Cohns website redesign").
Written against `docs/design-handoffs.md`. Nothing here ships as-is — the artboards use inline styles, which `style-src 'self'` forbids. Every visual below is named against a token or a class in `site/css/main.css`.

---

## 0. The one decision that needs sign-off first

**The site becomes light-first and drops `prefers-color-scheme` dark.**

The standing contract says design against a dark-first token table. This redesign deliberately overturns that: the ground is a warm cream, per the Organic design system chosen for the site. This is not a per-page palette — it is a redefinition of the six root tokens in `main.css`, so every existing page (résumé, recipes, classes, admin, gallery) inherits it without markup changes.

Concretely: **delete the `@media (prefers-color-scheme: light)` block** and replace the `:root` values. The variable names, the class layer, and the print block are unchanged.

Fonts stay the **system sans stack**. No self-hosted `@font-face`, no Google Fonts link — the Organic display face (Caprasimo) is *not* adopted. Weight and letter-spacing carry the display voice instead.

---

## 1. Fidelity note

**Exact:** all copy, the two-halves structure, the pill treatment of the skills list, heading hierarchy, and the token values in §3.

**Freely adapted:** mobile reflow (the two columns stack; breakpoint is engineering's call), exact rem rounding of the px values below, and photo crop.

**Not in scope:** no page loses or gains a section. Same content, same URLs, same order.

---

## 2. Token mapping

Replace the `:root` block at the top of `main.css`. Six existing tokens change value; five are new.

| Token | Current (dark) | New | Role |
|---|---|---|---|
| `--bg` | `#0f1115` | `#f5ead8` | cream page ground |
| `--surface` | `#171a21` | `#ebddc5` | sand panels, cards |
| `--border` | `#262b35` | `#c0b6a5` | hairlines, outlined controls |
| `--text` | `#e6e8ec` | `#201e1d` | body text |
| `--muted` | `#9aa3b2` | `#645c50` | secondary text |
| `--accent` | `#5eb0ef` | `#c67139` | terracotta: solid fills, eyebrows |
| `--accent-ink` | — | `#8c491a` | new. Accent at paragraph contrast — **use this for link text and any accent-colored copy**, never `--accent` (which is ~3:1 on cream: chrome and large text only) |
| `--accent-press` | — | `#b2622d` | new. Hover/pressed step for accent fills and links |
| `--accent-2` | — | `#7a8a5e` | new. Sage: the foodie half's voice |
| `--accent-2-ink` | — | `#56633f` | new. Sage at paragraph contrast — sage links and copy |
| `--accent-tint` | — | `#fff2eb` | new. Warm tint for pill fills |

Also change:

- `--max` stays `62rem` for prose pages. The home page and `/foodie` need a wider measure — add `--max-wide: 67.5rem` (1080px) and apply it the way `.page--gallery .wrap` already overrides `--max`.
- Radius: containers `2rem`, inner panels `1.5rem`, pills `999px`. The existing `12px` card radius steps up to `2rem` on the new panels; leave `.recipe-card` and friends at `12px` for now, or raise them all in a follow-up.
- Elevation: none. No box-shadows on either page — the panels separate by fill, not by shadow.
- Focus: keep a themed ring — `:focus-visible { outline: 2px solid var(--accent); outline-offset: 2px; }`.
- `::selection { background: var(--accent-tint); }`.

Existing classes that keep working unchanged once the tokens flip: `.wrap`, `.eyebrow`, `.tagline`, `.masthead--sub`, `footer`, `.recipe-notes`, `.affiliate-disclosure`, `.chip`, `.form-input`. **Reuse them.** The print block already forces its own light values and needs no edit.

---

## 3. Structure — home page (`site/index.html`)

Two halves of equal weight, side by side, each a filled rounded panel. Order top to bottom:

**Masthead** — full width, no bottom rule (the panels below do the separating).
- Eyebrow `cohns.net` — `.eyebrow`, `--accent-ink`, uppercase, `.12em` tracking, 12px.
- `h1` "Steven M. Cohn" — 68px desktop, `line-height: 1.02`, `letter-spacing: -.03em`, weight 800. Keep the existing `clamp()` approach, retuned to this ceiling.
- Tagline "DevOps & Site Reliability Engineer — Niwot, Colorado" — `.tagline`, 21px, `--muted`.
- Build note — `.build-note`, 16px, `--muted`, max 52ch, with the repo link inline.
- **Headshot** — 200px circle, right-aligned on the same baseline as the eyebrow, `border-radius: 999px`, `object-fit: cover`. Stacks under the text on mobile.

**Two-column grid** — `1fr 1fr`, `1.5rem` gap, `align-items: start`. One column below ~48rem.

**Left panel — Engineering.** Fill `--surface`, radius `2rem`, padding `2.75rem 2.5rem`, children stacked with a `1.75rem` gap.
- Kicker "The work" (`--accent-ink`, uppercase 11px) · `h2` "Engineering" 40px/800 · intro paragraph 17px `--text`.
- **Skills as pill tags** — replaces the current `.skills` hairline list. Six labelled groups, each a 11px uppercase `--muted` label above a wrapping row of pills. Pill: `--accent-tint` fill, `--accent-ink` text, 13px, `padding: 5px 13px`, `border-radius: 999px`, `gap: 6px`. Not interactive, not links.
- **Action row** — one solid pill (`--accent` fill, `#f9f4ed` text, hover `--accent-press`) for "Résumé →", then three outlined pills (`1px solid --border`, `--text`, hover fill `#e1d5bd`) for the repository, LinkedIn, and the mailto. `display: flex; flex-wrap: wrap; gap: 10px`.
- **Observability sub-panel** — nested block, fill `--bg`, radius `1.5rem`, padding `1.75rem`. `h3` 24px, body 15px `--muted`, then the text link "Open the live dashboards →".

**Right panel — Foodie.** Fill `#e1eecc` (sage tint — add as `--accent-2-tint`), radius `2rem`, same padding. This is the one place a second ground color appears on the page.
- Kicker "The other half" (`--accent-2-ink`) · `h2` "I'm a foodie" 40px/800 · intro 17px.
- **Food photograph** — 280px tall, full panel width, radius `1.5rem`, `object-fit: cover`.
- One solid sage pill "Recipes & classes →" (`--accent-2` fill, `#f0fae1` text, hover `#728157`).
- **Family sub-panel** — fill `#f0fae1`, radius `1.5rem`. `h3` "Family", body, link "Open the family library →" in `--accent-2-ink`.

**Say-hello strip** — full width under both columns, `--surface`, radius `2rem`, padding `2.5rem`. Heading and one line on the left, the "Coming soon" badge on the right. The badge is the existing `.soon`, restyled to a solid `--accent-tint` pill with `--accent-ink` text — no dashed border.

**Footer** — existing `footer`, no top rule, 14px `--muted`, the build line unchanged.

---

## 4. Structure — `/foodie` (`site/foodie/index.html`)

Same system, two photo-led cards. Uses `--max-wide`.

**Masthead** — `.masthead--sub`. Eyebrow is the back-link `cohns.net` (`--accent-ink`); `h1` "I'm a foodie" 64px/800; tagline "The recipes I cook and the classes I teach."

**Card grid** — `repeat(auto-fit, minmax(20rem, 1fr))`, `1.5rem` gap, `align-items: start`.

Both cards are structurally identical — that is the point, and it is a requirement below:

| | Recipes card | Classes card |
|---|---|---|
| Fill | `--accent-2-tint` `#e1eecc` | `--surface` |
| Photo | `beet-salad.jpg` | `img_7381.jpeg` |
| `h2` | "Recipes" | "Classes & workshops" |
| Body color | `#3d472b` | `--text` |
| Button | sage solid, "Browse recipes →" → `/recipes/` | accent solid, "See classes →" → `/classes/` |

Card: radius `2rem`, padding `2.5rem`, children stacked `1.5rem`. Photo first, then heading + body, then the pill (`align-self: flex-start`).

**Photo slot** — `height: 220px`, full card width, `border-radius: 1.5rem`, `overflow: hidden`, `img { width:100%; height:100%; object-fit: cover; object-position: center }`. Both slots are the same box; the images differ in source aspect ratio and are cropped to fit.

**Footer** — a single "← Back to cohns.net" link.

---

## 5. Copy — exact, final

Home page:
- Eyebrow: `cohns.net`
- H1: `Steven M. Cohn`
- Tagline: `DevOps & Site Reliability Engineer — Niwot, Colorado`
- Build note: `This site is built and deployed entirely from [a public Terraform repository](https://github.com/steve-cohn-personal/cohns-net-infra). The infrastructure is the portfolio.`
- Engineering kicker `The work`; H2 `Engineering`; body `Thirty years of building and running infrastructure — from Unix systems and Cisco networks to AWS organizations, Terraform module libraries, and Kubernetes clusters serving billions of requests a day.`
- Skill group labels: `Cloud` · `Orchestration` · `Containers` · `CI/CD` · `Data` · `Observability` (pill contents unchanged from the current `.skills` list)
- Actions: `Résumé →` · `Infrastructure repository` · `LinkedIn` · `steve@cohns.net`
- Observability: H3 `Observability`; body `This site watches itself. Live uptime, latency, and cost dashboards — global synthetic probes and CloudWatch, all defined as Terraform, served from Grafana Cloud on the free tier. You can watch the database scale to zero and the bill go with it.`; link `Open the live dashboards →`
- Foodie kicker `The other half`; H2 `I'm a foodie`; body `Recipes and video from the cooking I love, plus hands-on classes and workshops for groups of 1 to 100.`; button `Recipes & classes →`
- Family: H3 `Family`; body `A private photo library for family. Access by invitation.`; link `Open the family library →`
- Say hello: H2 `Say hello`; body `Comments and conversation will live here.`; badge `Coming soon`
- Footer: `Built with Terraform and Ansible on AWS. S3 · CloudFront · Route 53 · ACM · IAM Identity Center · GitHub OIDC.` (non-breaking spaces in `Route 53` and `GitHub OIDC`)

`/foodie`:
- H1 `I'm a foodie`; tagline `The recipes I cook and the classes I teach.`
- Recipes: H2 `Recipes`; body `The dishes from my cooking lessons — searchable, with ingredients, step-by-step method, photos, and lesson videos.`; button `Browse recipes →`
- Classes: H2 `Classes & workshops`; body `Hands-on cooking classes for groups of 1 to 100 — from paella to knife skills. Sign up for a scheduled session or request one.`; button `See classes →`
- Footer link `← Back to cohns.net`

---

## 6. Assets

Three photographs are in the design project and need to land in the repo under `site/img/` (served from `'self'`, so `img-src` is satisfied):

- `headshot.jpeg` — the home masthead circle. 800×800 square. Renders at 200px in a `border-radius: 999px` box, `object-fit: cover`, `object-position: center 20%` (the source has headroom; the offset centers the face).
- `beet-salad.jpg` — the recipes card and the home page's foodie photo slot
- `img_7381.jpeg` — the classes card

No outstanding assets.

---

## 7. Requirements to preserve

1. **No inline styles, no external fonts.** Everything above becomes named classes in `main.css`, keyed to the tokens in §2. System sans stack only.
2. **The token flip is global, not per-page.** Change `:root` once; do not fork a second palette for these two pages, and do not leave a dark `prefers-color-scheme` branch behind that would give the site two identities.
3. **`--accent` never carries body copy.** Paragraph-size accent text uses `--accent-ink` / `--accent-2-ink`. `--accent` is for fills, eyebrows, and large type.
4. **The two `/foodie` cards stay structurally identical** — same photo box, same order, same spacing. Only fill and content differ. Steve asked for this explicitly.
5. **Sage is the foodie voice, terracotta the engineering voice.** Don't mix them within a panel; the color is how the two halves stay legible as two halves.
6. **All existing URLs are unchanged**, including `/classes/class.html?slug=…`, which stays QR-safe per the standing contract.
7. **Every interactive element keeps a themed hover and a `:focus-visible` accent ring.** No browser-default focus rings.
