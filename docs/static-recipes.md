# Static recipe pages

`/recipes/` used to render entirely in the browser, so crawlers and link-preview bots saw
"Loading…". The deploy now pre-renders one crawlable page per recipe.

```
Aurora ──► GET api.cohns.net/recipes (public) ──► scripts/static-recipes/build.mjs ──► dist/site ──► S3
                                                          site/ is copied in first ──┘
```

## What gets built (into `dist/site`, gitignored)

| Output | Notes |
|---|---|
| `recipes/<slug>/index.html` | Full recipe in HTML (no JS needed), unique title/description, canonical, OG + Twitter tags, `Recipe` JSON-LD (+ nested `VideoObject`) |
| `recipes/index.html` | The tracked shell with the list pre-rendered between `<!--static:list-->` markers; `recipes.js` still layers search/filters on top |
| `sitemap.xml` | `/`, `/foodie/`, `/recipes/`, every recipe, `/classes/`. Never `/family/` |
| `robots.txt` | The tracked `site/robots.txt` in prod; the `Sitemap:` line is dropped in dev/stage |

Directory URLs (`/recipes/<slug>/` → `index.html`) are handled by the existing CloudFront
function in `terraform/modules/static-site` — no infrastructure change.

## Rules the build enforces

- **Fails** if a recipe has no name, no ingredients or no steps, a bad slug, or a duplicate slug; or if the API returns nothing.
- **Warns** (does not fail) when a recipe has no image. Google withholds the rich result for those
  pages, but they are still worth indexing. Image = hero photo, else the lesson video's poster frame.
  `check.mjs --require-image` makes it strict.
- Fields with no data are omitted from the JSON-LD, never guessed. Not in the API today:
  prep/cook/total time, `datePublished`, video `uploadDate`, gear. The generator already reads
  `prep_minutes`, `cook_minutes`, `total_minutes`, `created_at`, `updated_at` and `gear`
  (`[{name, url, note}]`) if the API starts returning them.
- Dev and stage pages are `noindex` and show the empty gear/signup slots for layout review. In prod
  those slots stay hidden until there is data (gear) or a form action (signup).

## Wiring the email signup

Set the repo/environment variable `EMAIL_SIGNUP_ACTION` to the provider's form POST URL and redeploy.
If the provider needs a `fetch()` instead of a form post, add its origin to `connect-src` in
`terraform/live/site/main.tf`.

## Freshness

Pages are as fresh as the last site deploy. A recipe published in `/admin` since then has no static
page yet; the list links it to the client-rendered `/recipes/recipe.html?slug=…` (which is `noindex`)
until the next deploy.

## Local use

```sh
node --test "scripts/static-recipes/test/*.test.mjs"          # unit tests
make build-site ENV=dev                           # build + validate into dist/site
(cd dist/site && python3 -m http.server 8765)     # look at it
```
