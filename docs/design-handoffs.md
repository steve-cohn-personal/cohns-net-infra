# Design Handoffs

**The goal: the design side hands off a *component contract* and a *token mapping* — never
shippable styles.** A Claude Design `.dc.html` artboard is a reference for structure, copy, and
proportion. It is not code that ships, and two hard constraints below mean it never can be. A good
handoff tells engineering *what to build and which existing pieces to map onto*, so recreating it in
the site's templates is a bounded job, not a re-negotiation.

This doc is the standing contract to design *against*. The first concrete instance — the class
`tools` field — is spelled out at the end; new layout-focused pieces should follow the same shape.

## The two constraints every handoff lives under

1. **The CSP forbids inline styles and external fonts.** The site ships this header (see
   [`terraform/live/site/main.tf`](../terraform/live/site/main.tf)):

   ```
   default-src 'self'; style-src 'self'; script-src 'self'; img-src 'self' data: …
   ```

   `style-src 'self'` kills both the `<style>` block *and* `style="…"` attributes an artboard emits.
   There is no `font-src`, so it falls back to `default-src 'self'` — a Google Fonts `<link>` and its
   font files are both blocked. **Consequence:** a paper-style handoff (Cormorant Garamond, IBM Plex
   Mono, a cream background baked into inline CSS) cannot render as-is. Its *palette and structure* can
   be mapped onto the site's system; its *fonts* cannot appear unless we deliberately self-host them as
   `@font-face` files — treat that as a separate, explicit decision, not a default.

2. **All CSS lives in one external file:** [`site/css/main.css`](../site/css/main.css). Anything the
   handoff needs that isn't already there becomes a small, named addition to that file, keyed off the
   site's design tokens. So the useful unit of a handoff is *"here is the structure, and here is which
   token / existing class each part maps to"* — not a pixel value.

## Design against these tokens, not the handout's palette

The site is **dark-first** with a light mode via `prefers-color-scheme`. Every color in a handoff
should map to one of these CSS variables (defined at the top of `main.css`), so the piece inherits the
site's identity and both themes for free:

| Token        | Role                                   | Dark      | Light     |
|--------------|----------------------------------------|-----------|-----------|
| `--bg`       | page background                        | `#0f1115` | `#fbfbfc` |
| `--surface`  | cards, raised blocks                   | `#171a21` | `#ffffff` |
| `--border`   | hairlines, rules, dividers             | `#262b35` | `#e3e6ea` |
| `--text`     | body text                              | `#e6e8ec` | `#1a1d23` |
| `--muted`    | secondary / descriptive text           | `#9aa3b2` | `#5d6673` |
| `--accent`   | links, active state, eyebrows          | `#5eb0ef` | `#1f6fb2` |

Type is the system sans stack (`ui-sans-serif, -apple-system, …`) — **no serif or display face is
loaded.** Reading width is `--max` (`62rem`), centered by `.wrap`.

**Reuse before inventing.** These classes already exist and cover most layout needs; a handoff should
name the ones it maps to:

- Page chrome: `.masthead.masthead--sub`, `.wrap`, `.eyebrow`, `.tagline`, `footer`
- Prose / authored Markdown: `.recipe-notes` (block), `.recipe-summary` (lead line)
- Cards & grids: `.card`, `.recipe-grid` + `.recipe-card` (auto-fill, `16rem` min)
- Affiliate: `.affiliate-disclosure` (the FTC line; auto-rendered, see below)

## Content is data; the artboard is the component

Design one **item component** plus its **container**, and treat the actual entries as data that fills
it. When the layout is reworked later, the component/artboard changes and the data model doesn't. That
separation is the whole reason a structured field beats prose: it gives design a stable thing to design
against and engineering a stable thing to render.

## Markdown links are auto-handled — never pre-tag a URL

The site renders authored text through [`site/js/md.js`](../site/js/md.js), a small Markdown subset.
Two behaviors matter for handoffs, and both mean **URLs are stored raw**:

- **External links** get `target="_blank" rel="noopener nofollow sponsored"` automatically.
- **Amazon links** get the Associates tag `stevecohnsnet-20` injected at render time.

So a handoff (and the stored data) carries the plain URL — e.g. `https://amzn.to/4xiAKsn`. Do **not**
append `?tag=…` in the design or the content; the site adds it. Any tool component that shows a link
should render its label through md.js inline so it inherits this handling for free.

---

## Contract: the class `tools` field

The first piece built to this pattern. A class (see [`services/comments-api`](../services/comments-api))
gains a `tools` field: the products used in that class, each linking to Amazon.

**Data shape** — a JSON array on the class; each item:

| Key    | Required | Notes                                                             |
|--------|----------|-------------------------------------------------------------------|
| `name` | yes      | Product name, e.g. `OXO angled jigger`. Rendered as the link text.|
| `url`  | yes      | Absolute `http(s)` link — normally an `amzn.to` short link. Raw, untagged. |
| `note` | no       | One line of description beneath the name. Muted.                  |

```json
"tools": [
  { "name": "OXO angled jigger",  "url": "https://amzn.to/4xiAKsn", "note": "Read the measure from above, without bending down." },
  { "name": "Mini biscuit cutter","url": "https://amzn.to/4ipSqNW", "note": "Cuts the rounds for the pita toasts and the canapés." }
]
```

**Where it renders.** On the class detail page (`/classes/class.html?slug=…`, driven by
[`site/js/classes.js`](../site/js/classes.js)), as its own section between the class `description` and
the "Upcoming sessions" block.

**Component to design** (this is what Claude Design owns):

- **Section** — a heading in the class-body voice (maps to the `h2`/`h3` inside `.recipe-notes`) plus an
  optional one-line intro (`--muted`). Working copy: heading *"Tools I used today"*, intro *"Nothing here
  is expensive or exotic — these are the tools we actually used in class."*
- **List container** — two columns at desktop (~`≥45rem`), one column below, using the site's reading
  width. Column/row gaps are the designer's call in *rem*, mapped when built.
- **Item** — a hairline top rule (`--border`), the `name` as a link, and the `note` beneath in
  `--muted`. Decide one thing explicitly: does the name read as an accent-colored link (`--accent`, site
  default) or as body text (`--text`) with underline-on-hover? Either is fine; pick one and it becomes
  the rule for every class.

**Behavior that's already wired, so don't re-spec it:**

- The **FTC affiliate disclosure** (`.affiliate-disclosure`) is appended automatically whenever a class
  body contains an Amazon link — `classes.js` already does this, mirroring the recipe pages. The handoff
  doesn't need to place it; it just needs to leave room for it under the list.
- **New-tab, `rel="sponsored"`, and the affiliate tag** come from md.js as above.

**Requirements to preserve** (these are non-negotiable and outlive any layout):

1. The affiliate disclosure stays visible on any page carrying an Amazon link.
2. Stored URLs stay raw `amzn.to` links — untagged, unstripped.
3. The class detail URL is the stable, QR-safe address for a printed handout:
   `https://steve.cohns.net/classes/class.html?slug=<slug>`. It must not move once a QR is printed.

## What a finished handoff bundle contains

Mirror the shape of the first one, pointed at a field/component instead of a standalone page:

1. **Fidelity note** — what's exact (copy, proportion) vs. freely adapted (mobile reflow).
2. **Structure** — the component + container, top to bottom.
3. **Token mapping** — each visual choice named against the table above (or an existing class), not a
   hex value or a font file.
4. **The field contract** — the data shape the component renders, if it's data-driven.
5. **Copy** — exact, final strings.
6. **Requirements to preserve** — the handful of things (like the three above) that must survive any
   redesign.
