#!/usr/bin/env node
// Verify a built site dir: every recipe page carries parseable, complete Recipe JSON-LD
// and the on-page SEO tags; the index links every recipe; the sitemap and robots are right.
//
//   node scripts/static-recipes/check.mjs [dist/site] [--env prod] [--require-image]
//
// Image is a warning unless --require-image (see validateRecipe for why).

import { existsSync, readdirSync, readFileSync, statSync } from "node:fs";
import { join, resolve } from "node:path";

const argv = process.argv.slice(2);
const flag = (n) => argv.includes(`--${n}`);
const opt = (n, d) => (argv.includes(`--${n}`) ? argv[argv.indexOf(`--${n}`) + 1] : d);
const positional = argv.filter((a, i) => !a.startsWith("--") && !["--env", "--origin"].includes(argv[i - 1]));
const dir = resolve(positional[0] || "dist/site");
const env = opt("env", "dev");
const origin = opt("origin", "https://steve.cohns.net");

const errors = [], warnings = [];
const fail = (m) => errors.push(m);

const slugs = readdirSync(join(dir, "recipes")).filter((n) => statSync(join(dir, "recipes", n)).isDirectory());
if (!slugs.length) fail("no recipe pages found");

const titles = new Map(), descs = new Map();
const attr = (html, re) => (html.match(re) || [])[1];
const ISO_DURATION = /^P(?!$)(\d+D)?(T(?=\d)(\d+H)?(\d+M)?(\d+S)?)?$/;

for (const slug of slugs) {
  const file = join(dir, "recipes", slug, "index.html");
  if (!existsSync(file)) { fail(`${slug}: no index.html`); continue; }
  const html = readFileSync(file, "utf8");
  const at = (m) => `${slug}: ${m}`;

  const blocks = [...html.matchAll(/<script type="application\/ld\+json">([\s\S]*?)<\/script>/g)];
  if (blocks.length !== 1) { fail(at(`expected 1 JSON-LD block, found ${blocks.length}`)); continue; }
  let ld;
  try { ld = JSON.parse(blocks[0][1]); } catch (e) { fail(at(`JSON-LD does not parse: ${e.message}`)); continue; }

  if (ld["@type"] !== "Recipe") fail(at("JSON-LD @type is not Recipe"));
  if (!ld.name) fail(at("JSON-LD missing name"));
  if (ld.author?.name !== "Steven M. Cohn") fail(at("JSON-LD author missing/wrong"));
  if (!Array.isArray(ld.recipeIngredient) || !ld.recipeIngredient.length) fail(at("JSON-LD missing recipeIngredient"));
  if (!Array.isArray(ld.recipeInstructions) || !ld.recipeInstructions.length
      || ld.recipeInstructions.some((s) => s["@type"] !== "HowToStep" || !s.text)) fail(at("JSON-LD recipeInstructions must be HowToStep[] with text"));
  if (!ld.image?.length) (flag("require-image") ? fail : (m) => warnings.push(m))(at("no image (not rich-result eligible)"));
  for (const k of ["prepTime", "cookTime", "totalTime"]) if (ld[k] && !ISO_DURATION.test(ld[k])) fail(at(`${k} is not ISO 8601: ${ld[k]}`));
  if (ld.video) for (const k of ["name", "thumbnailUrl", "contentUrl"]) if (!ld.video[k]) fail(at(`VideoObject missing ${k}`));
  for (const [k, v] of Object.entries(ld)) if (v == null || v === "" || (Array.isArray(v) && !v.length)) fail(at(`JSON-LD has empty ${k} (omit instead)`));

  // On-page tags.
  const canonical = attr(html, /<link rel="canonical" href="([^"]+)"/);
  if (canonical !== `${origin}/recipes/${slug}/`) fail(at(`canonical is ${canonical}`));
  const title = attr(html, /<title>([^<]+)<\/title>/), desc = attr(html, /<meta name="description" content="([^"]*)"/);
  if (!title) fail(at("no <title>")); else titles.set(title, [...(titles.get(title) || []), slug]);
  if (!desc) fail(at("no meta description")); else descs.set(desc, [...(descs.get(desc) || []), slug]);
  for (const p of ["og:title", "og:description", "og:url"]) if (!html.includes(`property="${p}"`)) fail(at(`missing ${p}`));
  if (!html.includes('name="twitter:card"')) fail(at("missing twitter:card"));
  if (ld.image?.length && !html.includes('property="og:image"')) fail(at("has an image but no og:image"));
  if (env !== "prod" && !html.includes('name="robots" content="noindex"')) fail(at("non-prod page lacks noindex"));
  if (env === "prod" && html.includes('content="noindex"')) fail(at("prod page is noindex"));

  // Content must be in the HTML itself, not injected later.
  for (const needle of [ld.recipeIngredient?.[0], ld.recipeInstructions?.[0]?.text]) {
    if (needle && !html.includes(needle.slice(0, 24).replace(/&/g, "&amp;"))) warnings.push(at(`"${needle.slice(0, 24)}" not found verbatim in body (markup/escaping?)`));
  }
  for (const slot of ['data-slot="gear"', 'data-slot="email-signup"', 'href="/classes/"']) if (!html.includes(slot)) fail(at(`missing ${slot}`));
  const hasAffiliate = /href="https?:\/\/(?:[^"\/]*\.)?(amazon\.[a-z.]+|amzn\.to|amzn\.com)\//i.test(html);
  if (hasAffiliate && !html.includes("As an Amazon Associate I earn from qualifying purchases.")) fail(at("Amazon link without the disclosure"));
  if (hasAffiliate && !/tag=stevecohnsnet-20/.test(html)) fail(at("Amazon link without the affiliate tag"));
}
for (const [what, m] of [["title", titles], ["description", descs]]) {
  for (const [v, who] of m) if (who.length > 1) fail(`duplicate ${what} on ${who.join(", ")}: ${v.slice(0, 60)}`);
}

// Index: plain links to every recipe.
const index = readFileSync(join(dir, "recipes", "index.html"), "utf8");
for (const slug of slugs) if (!index.includes(`href="/recipes/${slug}/"`)) fail(`index: no link to /recipes/${slug}/`);

// Sitemap / robots.
const sitemap = readFileSync(join(dir, "sitemap.xml"), "utf8");
const locs = [...sitemap.matchAll(/<loc>([^<]+)<\/loc>/g)].map((m) => m[1]);
for (const p of ["/", "/foodie/", "/recipes/", "/classes/", ...slugs.map((s) => `/recipes/${s}/`)]) if (!locs.includes(origin + p)) fail(`sitemap: missing ${origin + p}`);
if (locs.some((l) => l.includes("/family"))) fail("sitemap: includes /family/");
if (locs.length !== slugs.length + 4) fail(`sitemap: expected ${slugs.length + 4} urls, found ${locs.length}`);
const robots = readFileSync(join(dir, "robots.txt"), "utf8");
if (!/^Disallow: \/family\/$/m.test(robots)) fail("robots.txt: /family/ is not disallowed");
if (env === "prod" && !robots.includes(`Sitemap: ${origin}/sitemap.xml`)) fail("robots.txt: prod is missing the Sitemap line");
if (env !== "prod" && /^Sitemap:/m.test(robots)) fail("robots.txt: non-prod advertises a sitemap");

if (warnings.length) console.warn(`warning: ${warnings.length} warning(s), first: ${warnings[0]}`);
if (errors.length) { errors.forEach((e) => console.error("error:", e)); console.error(`\n${errors.length} problem(s) in ${slugs.length} pages`); process.exit(1); }
console.log(`ok: ${slugs.length} recipe pages, JSON-LD complete, index/sitemap/robots consistent (${warnings.length} warning(s))`);
