#!/usr/bin/env node
// Build the static, crawlable recipe pages.
//
//   node scripts/static-recipes/build.mjs [--env dev|stage|prod] [--out dist/site]
//        [--api https://api.cohns.net] [--input recipes.json] [--categories cats.json]
//
// Copies site/ to the output dir, then adds /recipes/<slug>/index.html for every published
// recipe, a pre-rendered /recipes/ index, sitemap.xml and robots.txt. The deploy syncs
// the output dir. Recipes are read from the public API (no credentials) or from --input.
// Exits non-zero if any recipe is missing its name, ingredients or instructions.

import { cpSync, existsSync, mkdirSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import {
  buildSitemap, fillMarked, jsonForScript, loadMd, renderIndexList, renderRecipePage, robotsFor, validateRecipe,
} from "./lib.mjs";

const ROOT = resolve(dirname(fileURLToPath(import.meta.url)), "../..");

function parseArgs(argv) {
  const a = {};
  for (let i = 0; i < argv.length; i++) {
    if (!argv[i].startsWith("--")) throw new Error(`unexpected argument ${argv[i]}`);
    a[argv[i].slice(2)] = argv[++i];
  }
  return a;
}

async function getJson(url) {
  const res = await fetch(url, { headers: { accept: "application/json" }, signal: AbortSignal.timeout(30_000) });
  if (!res.ok) throw new Error(`GET ${url} -> ${res.status}`);
  return res.json();
}

async function main() {
  const args = parseArgs(process.argv.slice(2));
  const env = args.env || process.env.SITE_ENV || "dev";
  if (!["dev", "stage", "prod"].includes(env)) throw new Error(`--env must be dev|stage|prod, got ${env}`);
  const origin = (args.origin || process.env.SITE_ORIGIN || "https://steve.cohns.net").replace(/\/$/, "");
  const api = (args.api || process.env.RECIPES_API_URL || "https://api.cohns.net").replace(/\/$/, "");
  const out = resolve(ROOT, args.out || "dist/site");
  const signupAction = process.env.EMAIL_SIGNUP_ACTION || "";

  // --- load ---
  const recipes = args.input ? JSON.parse(readFileSync(args.input, "utf8")) : await getJson(`${api}/recipes`);
  if (!Array.isArray(recipes) || recipes.length === 0) throw new Error("no recipes returned — refusing to publish an empty library");
  let categories;
  try {
    categories = args.categories ? JSON.parse(readFileSync(args.categories, "utf8")) : await getJson(`${api}/recipes/categories`);
  } catch (e) {
    console.warn(`warning: categories unavailable (${e.message}); using the order found in the recipes`);
    categories = [...new Set(recipes.map((r) => r.category).filter(Boolean))];
  }
  recipes.sort((a, b) => a.title.localeCompare(b.title));

  // --- validate everything before writing anything ---
  const errors = [], warnings = [], seen = new Set();
  for (const r of recipes) {
    const v = validateRecipe(r);
    errors.push(...v.errors); warnings.push(...v.warnings);
    if (seen.has(r.slug)) errors.push(`${r.slug}: duplicate slug`);
    seen.add(r.slug);
  }
  if (warnings.length) console.warn(`warning: ${warnings.length} recipe(s) have no image and are not rich-result eligible:\n  ${warnings.map((w) => w.split(":")[0]).join("\n  ")}`);
  if (errors.length) {
    errors.forEach((e) => console.error("error:", e));
    throw new Error(`${errors.length} recipe(s) failed validation — fix them in /admin`);
  }

  // --- output tree ---
  rmSync(out, { recursive: true, force: true });
  cpSync(join(ROOT, "site"), out, { recursive: true });

  const md = await loadMd(origin);
  const opts = { origin, md, noindex: env !== "prod", showEmptySlots: env !== "prod", signupAction };

  for (const r of recipes) {
    const dir = join(out, "recipes", r.slug);
    mkdirSync(dir, { recursive: true });
    writeFileSync(join(dir, "index.html"), renderRecipePage(r, opts));
  }

  const indexPath = join(out, "recipes", "index.html");
  let index = readFileSync(indexPath, "utf8");
  index = fillMarked(index, "list", renderIndexList(recipes, categories, md));
  index = fillMarked(index, "slugs", `<script type="application/json" id="static-slugs">${jsonForScript(recipes.map((r) => r.slug))}</script>`);
  if (env !== "prod") index = index.replace("</title>", "</title>\n  <meta name=\"robots\" content=\"noindex\">");
  writeFileSync(indexPath, index);

  writeFileSync(join(out, "sitemap.xml"), buildSitemap(recipes, origin));
  writeFileSync(join(out, "robots.txt"), robotsFor(env, readFileSync(join(ROOT, "site/robots.txt"), "utf8")));

  const withImage = recipes.filter((r) => r.hero_image_url || r.video_key).length;
  console.log(`built ${recipes.length} recipe pages (${withImage} with an image) for ${env} -> ${out}`);
}

main().catch((e) => { console.error(e.message); process.exit(1); });
