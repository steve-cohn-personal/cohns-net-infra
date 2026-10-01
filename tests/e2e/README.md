# cohns.net end-to-end tests

Cypress specs that run against the **live** site (no local server).

| Folder | Runs against | Why |
|---|---|---|
| `cypress/e2e/site/` | prod or dev | Static pages, navigation, signed-out access control. No API needed. |
| `cypress/e2e/live-api/` | **prod only** | Recipes and classes come from `api.cohns.net`; dev has no API. |

```bash
npm ci
npm run cy:open      # interactive, prod
npm run cy:run       # everything, prod
npm run cy:run:dev   # site/ specs only, dev
```

Signups and class requests are deliberately not exercised: they POST to prod and email the owner.

## CI

`.github/workflows/e2e.yml` runs the `site/` specs against dev after every `deploy-site`, and
everything against prod nightly (or on demand via *Run workflow*).

Cypress Cloud recording is opt-in: set repo **variable** `CYPRESS_PROJECT_ID` and repo **secret**
`CYPRESS_RECORD_KEY`. Without both, CI runs unrecorded. Never commit the record key — this repo is public.
