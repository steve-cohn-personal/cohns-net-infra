// Pure functions behind the static recipe build. No I/O here, so the unit tests can
// drive everything with plain objects. build.mjs does the fetching and file writes.
//
// Markdown is rendered with the site's own md.js (loaded by loadMd below) so a static
// page and the live client-side page can never disagree on links, escaping, or the
// Amazon affiliate tag.

import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

export const AUTHOR = "Steven M. Cohn";
export const SLUG_RE = /^[a-z0-9][a-z0-9-]*$/;
const MEDIA_CDN = "https://media.cohns.net";
export const DISCLOSURE = "As an Amazon Associate I earn from qualifying purchases.";

// --- md.js ---------------------------------------------------------------------

let mdCache = null;
// md.js is a browser IIFE that hangs itself off window.cohnsMD and reads location.origin
// to resolve relative URLs. Give it both, import it once, and hand back the API.
export async function loadMd(origin) {
  if (mdCache) return mdCache;
  globalThis.window = globalThis.window || {};
  globalThis.location = { origin };
  await import(fileURLToPath(new URL("../../site/js/md.js", import.meta.url)));
  mdCache = globalThis.window.cohnsMD;
  return mdCache;
}

// --- small helpers -------------------------------------------------------------

export function esc(s) {
  return String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}

// Markdown -> plain text, for JSON-LD, <meta> and OG fields (which must not carry markup).
export function mdToText(md) {
  return String(md ?? "")
    .replace(/\[([^\]]+)\]\(([^)\s]+)\)/g, "$1")
    .replace(/`([^`]+)`/g, "$1")
    .replace(/\*\*([^*]+)\*\*/g, "$1")
    .replace(/(^|[^*])\*(?!\s)([^*]+?)\*/g, "$1$2")
    .replace(/(^|[^\w])_([^_\s][^_]*?)_(?![\w])/g, "$1$2")
    .replace(/^\s*#{1,6}\s+/gm, "")
    .replace(/^\s*[-*]\s+/gm, "")
    .replace(/\s+/g, " ")
    .trim();
}

export function truncate(text, max = 155) {
  if (text.length <= max) return text;
  const cut = text.slice(0, max - 1);
  return cut.slice(0, cut.lastIndexOf(" ") > 60 ? cut.lastIndexOf(" ") : cut.length).replace(/[\s,;:.-]+$/, "") + "…";
}

// JSON that is safe inside <script>: "<" can never start "</script>" or "<!--".
export function jsonForScript(obj) {
  return JSON.stringify(obj).replace(/</g, "\\u003c").replace(/\u2028/g, "\\u2028").replace(/\u2029/g, "\\u2029");
}

// Whole minutes -> ISO 8601 duration ("PT1H30M"). null for anything that isn't a positive number.
export function isoDuration(minutes) {
  const m = Number(minutes);
  if (!Number.isFinite(m) || m <= 0) return null;
  const h = Math.floor(m / 60), r = Math.round(m % 60);
  return "PT" + (h ? h + "H" : "") + (r ? r + "M" : "");
}

export function posterUrl(videoKey) {
  const name = videoKey.split("/").pop();
  return `${MEDIA_CDN}/${videoKey}/thumb/${name}_poster.0000000.jpg`;
}
export function hlsUrl(videoKey) {
  const name = videoKey.split("/").pop();
  return `${MEDIA_CDN}/${videoKey}/hls/${name}.m3u8`;
}

// The recipe's image: its hero photo, else the lesson video's poster frame (real media,
// not an invention). null when it has neither.
export function imageOf(r) {
  return r.hero_image_url || (r.video_key ? posterUrl(r.video_key) : null);
}

export function recipeUrl(origin, slug) {
  return `${origin}/recipes/${slug}/`;
}

// --- validation ----------------------------------------------------------------

// Returns { errors: [...], warnings: [...] }. Errors fail the build; warnings don't.
// An image is a warning, not an error: most of the library has no photo yet, and Google
// only withholds the rich result for those pages — they are still worth indexing.
export function validateRecipe(r) {
  const errors = [], warnings = [];
  const id = r && r.slug ? r.slug : "(no slug)";
  if (!r || typeof r.slug !== "string" || !SLUG_RE.test(r.slug)) errors.push(`${id}: slug must match ${SLUG_RE}`);
  if (!r || !String(r.title ?? "").trim()) errors.push(`${id}: missing name (title)`);
  if (!Array.isArray(r?.ingredients) || !r.ingredients.some((s) => String(s).trim())) errors.push(`${id}: no ingredients`);
  if (!Array.isArray(r?.steps) || !r.steps.some((s) => String(s).trim())) errors.push(`${id}: no instructions (steps)`);
  if (r && !imageOf(r)) warnings.push(`${id}: no image — page is built but not eligible for a Google recipe rich result`);
  return { errors, warnings };
}

// --- JSON-LD -------------------------------------------------------------------

export function buildJsonLd(r, origin) {
  const url = recipeUrl(origin, r.slug);
  const image = imageOf(r);
  const description = mdToText(r.summary);
  const ld = {
    "@context": "https://schema.org",
    "@type": "Recipe",
    "@id": url + "#recipe",
    mainEntityOfPage: url,
    name: r.title.trim(),
  };
  if (image) ld.image = [image];
  if (description) ld.description = description;
  ld.author = { "@type": "Person", name: AUTHOR };
  if (r.created_at) ld.datePublished = String(r.created_at).slice(0, 10);

  const prep = isoDuration(r.prep_minutes), cook = isoDuration(r.cook_minutes);
  const total = isoDuration(r.total_minutes ?? ((Number(r.prep_minutes) || 0) + (Number(r.cook_minutes) || 0)));
  if (prep) ld.prepTime = prep;
  if (cook) ld.cookTime = cook;
  if (total && (prep || cook || r.total_minutes)) ld.totalTime = total;

  // servings defaults to 1 when the yield is unknown (migration 0008), so 1 is not data.
  if (Number(r.servings) > 1) ld.recipeYield = `${r.servings} servings`;
  ld.recipeIngredient = r.ingredients.map(mdToText).filter(Boolean);
  ld.recipeInstructions = r.steps.map(mdToText).filter(Boolean).map((text, i) => ({
    "@type": "HowToStep", position: i + 1, text,
  }));
  if (r.category) ld.recipeCategory = r.category;
  if (r.cuisine) ld.recipeCuisine = r.cuisine;
  const keywords = [r.category, r.cuisine].filter(Boolean);
  if (keywords.length) ld.keywords = keywords.join(", ");

  if (r.video_key) {
    const video = { "@type": "VideoObject", name: r.title.trim(), thumbnailUrl: posterUrl(r.video_key), contentUrl: hlsUrl(r.video_key) };
    if (description) video.description = description;
    // No uploadDate until the API exposes timestamps — Google wants it, but we won't guess.
    if (r.video_uploaded_at || r.updated_at) video.uploadDate = String(r.video_uploaded_at || r.updated_at).slice(0, 10);
    ld.video = video;
  }
  return ld;
}

// --- page chrome ---------------------------------------------------------------

function metaDescription(r) {
  const s = mdToText(r.summary);
  if (s) return truncate(s);
  const bits = [r.cuisine, r.category].filter(Boolean).join(" ").toLowerCase();
  return truncate(`${r.title.trim()}${bits ? ` — a ${bits} recipe` : " — a recipe"} from Steve Cohn's cooking classes: ${r.ingredients.length} ingredients, ${r.steps.length} steps.`);
}

function headTags({ title, description, canonical, image, imageAlt, ogType, noindex }) {
  const t = [
    `<meta charset="utf-8">`,
    `<meta name="viewport" content="width=device-width, initial-scale=1">`,
    `<title>${esc(title)}</title>`,
    `<meta name="description" content="${esc(description)}">`,
    `<link rel="canonical" href="${esc(canonical)}">`,
  ];
  if (noindex) t.push(`<meta name="robots" content="noindex">`);
  t.push(
    `<link rel="icon" href="/favicon.svg" type="image/svg+xml">`,
    `<meta property="og:site_name" content="cohns.net">`,
    `<meta property="og:type" content="${ogType}">`,
    `<meta property="og:title" content="${esc(title)}">`,
    `<meta property="og:description" content="${esc(description)}">`,
    `<meta property="og:url" content="${esc(canonical)}">`,
    `<meta name="twitter:card" content="${image ? "summary_large_image" : "summary"}">`,
    `<meta name="twitter:title" content="${esc(title)}">`,
    `<meta name="twitter:description" content="${esc(description)}">`,
  );
  if (image) {
    t.push(
      `<meta property="og:image" content="${esc(image)}">`,
      `<meta property="og:image:alt" content="${esc(imageAlt)}">`,
      `<meta name="twitter:image" content="${esc(image)}">`,
      `<meta name="twitter:image:alt" content="${esc(imageAlt)}">`,
    );
  }
  t.push(`<link rel="stylesheet" href="/css/main.css">`);
  return t.join("\n  ");
}

// --- recipe page ---------------------------------------------------------------

function gearList(r, md) {
  const gear = Array.isArray(r.gear) ? r.gear.filter((g) => g && g.name && g.url) : [];
  return gear.map((g) => ({
    html: md.renderInline(`[${String(g.name).replace(/[\[\]]/g, "")}](${String(g.url).replace(/[\s()]/g, (c) => (c === "(" ? "%28" : c === ")" ? "%29" : "%20"))})`),
    note: g.note ? String(g.note) : "",
  }));
}

function hasAmazonLink(html, md) {
  for (const m of html.matchAll(/href="([^"]+)"/g)) {
    if (md.isAmazonUrl(m[1])) return true;
  }
  return false;
}

// opts: { origin, md, noindex, showEmptySlots, signupAction }
export function renderRecipePage(r, opts) {
  const { origin, md } = opts;
  const url = recipeUrl(origin, r.slug);
  const image = imageOf(r);
  const title = `${r.title.trim()} — cohns.net`;
  const description = metaDescription(r);
  const ld = buildJsonLd(r, origin);
  const hasVideo = !!r.video_key;

  const body = [];
  if (r.category) body.push(`<p class="recipe-category"><a href="/recipes/?category=${encodeURIComponent(r.category)}">${esc(r.category)}</a></p>`);
  body.push(`<h1>${esc(r.title.trim())}</h1>`);
  const meta = [];
  if (r.cuisine) meta.push(`<a class="recipe-tag" href="/recipes/?cuisine=${encodeURIComponent(r.cuisine)}">${esc(r.cuisine)}</a>`);
  if (r.difficulty) meta.push(`<span class="recipe-tag recipe-tag--plain">${esc(r.difficulty)}</span>`);
  if (meta.length) body.push(`<p class="recipe-meta">${meta.join("")}</p>`);
  // The hero is the likely LCP element: eager + high priority, never lazy.
  if (r.hero_image_url) body.push(`<img class="recipe-hero" src="${esc(r.hero_image_url)}" alt="${esc(r.title.trim())}" fetchpriority="high">`);
  if (r.summary) body.push(`<p class="recipe-summary">${md.renderInline(r.summary)}</p>`);
  if (r.notes) body.push(`<div class="recipe-notes">${md.render(r.notes)}</div>`);

  if (hasVideo) {
    body.push(
      `<div class="recipe-video-wrap">`,
      `<video class="recipe-video" controls playsinline preload="none" poster="${esc(posterUrl(r.video_key))}" data-hls="${esc(hlsUrl(r.video_key))}">`,
      `<source src="${esc(hlsUrl(r.video_key))}" type="application/vnd.apple.mpegurl">`,
      `<a href="${esc(hlsUrl(r.video_key))}">Watch the lesson video</a>`,
      `</video></div>`,
    );
  }

  body.push(`<h2>Ingredients</h2>`);
  if (Number(r.servings) > 1) body.push(`<p class="recipe-yield">Makes ${Number(r.servings)} servings</p>`);
  body.push(`<ul class="ingredients">${r.ingredients.map((i) => `<li>${md.renderInline(i)}</li>`).join("")}</ul>`);
  body.push(`<h2>Method</h2>`);
  body.push(`<ol class="steps">${r.steps.map((s) => `<li>${md.renderInline(s)}</li>`).join("")}</ol>`);

  // --- monetization slots ---
  const gear = gearList(r, md);
  if (gear.length) {
    body.push(
      `<section class="recipe-gear" data-slot="gear"><h2>Gear used</h2><ul class="class-tools">`,
      ...gear.map((g) => `<li><span class="class-tool-name">${g.html}</span>${g.note ? `<span class="class-tool-note">${esc(g.note)}</span>` : ""}</li>`),
      `</ul></section>`,
    );
  } else {
    // Empty slot: in the DOM for when gear data arrives, visible only where we're reviewing layout.
    body.push(`<section class="recipe-gear" data-slot="gear"${opts.showEmptySlots ? "" : " hidden"}><h2>Gear used</h2><p class="recipe-slot-note">Placeholder — no gear listed for this recipe yet.</p></section>`);
  }

  const wired = !!opts.signupAction;
  body.push(
    `<section class="recipe-signup" data-slot="email-signup"${wired || opts.showEmptySlots ? "" : " hidden"}>`,
    `<h2>Get new recipes by email</h2>`,
    `<form class="recipe-signup-form" action="${esc(wired ? opts.signupAction : "#")}" method="post">`,
    `<label for="signup-email">Email address</label>`,
    `<input class="form-input" id="signup-email" name="email" type="email" autocomplete="email" required>`,
    `<button class="btn" type="submit"${wired ? "" : " disabled"}>Subscribe</button>`,
    `</form>`,
    wired ? "" : `<p class="recipe-slot-note">Placeholder — not wired to an email provider yet.</p>`,
    `</section>`,
  );
  body.push(`<p class="recipe-cta"><a class="pill pill--solid" href="/classes/">Book a class</a></p>`);

  const inner = body.join("\n    ");
  // Disclosure is decided from the rendered output, so it appears iff an Amazon link does.
  if (hasAmazonLink(inner, md)) body.push(`<p class="affiliate-disclosure">${DISCLOSURE}</p>`);

  // Data the progressive enhancement needs (raw Markdown for the servings scaler).
  const data = { slug: r.slug, servings: Math.max(1, parseInt(r.servings, 10) || 1), ingredients: r.ingredients };

  return `<!doctype html>
<html lang="en">
<head>
  ${headTags({ title, description, canonical: url, image, imageAlt: r.title.trim(), ogType: "article", noindex: opts.noindex })}
  <script type="application/ld+json">${jsonForScript(ld)}</script>
</head>
<body>
  <header class="masthead masthead--sub">
    <div class="wrap">
      <div id="authbar" class="authbar"></div>
      <p class="eyebrow"><a href="/recipes/">← Recipes</a></p>
    </div>
  </header>

  <main class="wrap">
    <article id="recipe-detail" class="recipe-detail" data-static="1">
    ${body.join("\n    ")}
    </article>
    <script type="application/json" id="recipe-data">${jsonForScript(data)}</script>
  </main>

  <footer class="wrap">
    <p><a href="/recipes/">← All recipes</a></p>
  </footer>

  <script src="/js/auth.js"></script>${hasVideo ? `\n  <script src="/vendor/hls.min.js"></script>` : ""}
  <script src="/js/md.js"></script>
  <script src="/js/recipes.js"></script>
</body>
</html>
`;
}

// --- index page ----------------------------------------------------------------

const OTHER = "Other";

export function groupByCategory(recipes, categories) {
  const groups = new Map();
  for (const r of recipes) {
    const key = r.category && categories.includes(r.category) ? r.category : OTHER;
    if (!groups.has(key)) groups.set(key, []);
    groups.get(key).push(r);
  }
  return [...categories, OTHER].filter((c) => groups.has(c)).map((c) => ({ category: c, recipes: groups.get(c) }));
}

// The list markup mirrors recipes.js's recipeCard/orderedGroups so the JS repaint is invisible.
export function renderIndexList(recipes, categories, md) {
  return groupByCategory(recipes, categories).map((g) => {
    const cards = g.recipes.map((r) => {
      const thumb = r.hero_image_url ? `<img class="recipe-card-thumb" src="${esc(r.hero_image_url)}" alt="" loading="lazy">` : "";
      return `<a class="recipe-card${r.hero_image_url ? " has-thumb" : ""}" href="/recipes/${r.slug}/">${thumb}<h3>${esc(r.title.trim())}</h3><p>${esc(mdToText(r.summary))}</p></a>`;
    }).join("\n      ");
    return `<section class="recipe-group"><h2>${esc(g.category)}</h2>\n    <div class="recipe-grid">\n      ${cards}\n    </div></section>`;
  }).join("\n    ");
}

// Replace the marked region of the tracked shell page. Throws if the marker is gone, so
// a template edit can't silently ship an index with no recipes in it.
export function fillMarked(html, name, replacement) {
  const re = new RegExp(`<!--static:${name}-->[\\s\\S]*?<!--/static:${name}-->`);
  if (!re.test(html)) throw new Error(`template is missing <!--static:${name}--> markers`);
  return html.replace(re, () => `<!--static:${name}-->${replacement}<!--/static:${name}-->`);
}

// --- sitemap / robots ----------------------------------------------------------

export function buildSitemap(recipes, origin) {
  const paths = ["/", "/foodie/", "/recipes/", ...recipes.map((r) => `/recipes/${r.slug}/`), "/classes/"];
  const urls = paths.map((p) => {
    const rec = recipes.find((r) => p === `/recipes/${r.slug}/`);
    const last = rec && rec.updated_at ? `<lastmod>${esc(String(rec.updated_at).slice(0, 10))}</lastmod>` : "";
    return `  <url><loc>${esc(origin + p)}</loc>${last}</url>`;
  });
  return `<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n${urls.join("\n")}\n</urlset>\n`;
}

// The tracked robots.txt is the prod file. Elsewhere we drop its Sitemap line: dev/stage
// must not advertise a sitemap (pages there also carry noindex).
export function robotsFor(env, tracked) {
  return env === "prod" ? tracked : tracked.replace(/^Sitemap:.*\n?/gim, "");
}
