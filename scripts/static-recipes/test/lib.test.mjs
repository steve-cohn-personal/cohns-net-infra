import test from "node:test";
import assert from "node:assert/strict";
import {
  buildJsonLd, buildSitemap, fillMarked, groupByCategory, isoDuration, jsonForScript, loadMd, mdToText,
  renderRecipePage, robotsFor, validateRecipe, DISCLOSURE,
} from "../lib.mjs";

const ORIGIN = "https://steve.cohns.net";
const md = await loadMd(ORIGIN);
const base = () => ({
  slug: "simple-syrup", title: "Simple Syrup", category: "Quick Meals", cuisine: null, difficulty: null,
  summary: "Equal parts **sugar** and water.", notes: null, servings: 1,
  ingredients: ["1 cup sugar", "1 cup water"], steps: ["Heat.", "Cool."], hero_image_url: null, video_key: null,
});
const page = (r, o = {}) => renderRecipePage(r, { origin: ORIGIN, md, noindex: false, showEmptySlots: false, signupAction: "", ...o });

test("validateRecipe: name, ingredients and steps are errors; a missing image is only a warning", () => {
  assert.deepEqual(validateRecipe(base()).errors, []);
  assert.equal(validateRecipe(base()).warnings.length, 1);
  for (const [k, v] of [["title", " "], ["ingredients", []], ["steps", [""]], ["slug", "../etc"]]) {
    assert.equal(validateRecipe({ ...base(), [k]: v }).errors.length, 1, k);
  }
});

test("validateRecipe: a video poster counts as an image", () => {
  assert.deepEqual(validateRecipe({ ...base(), video_key: "lessons/x" }).warnings, []);
});

test("JSON-LD omits what it doesn't know and never invents", () => {
  const ld = buildJsonLd(base(), ORIGIN);
  for (const k of ["image", "prepTime", "cookTime", "totalTime", "recipeYield", "datePublished", "recipeCuisine", "video"]) assert.ok(!(k in ld), k);
  assert.equal(ld.description, "Equal parts sugar and water.");
  assert.equal(ld.author.name, "Steven M. Cohn");
  assert.deepEqual(ld.recipeInstructions.map((s) => s.text), ["Heat.", "Cool."]);
  assert.equal(ld.recipeCategory, "Quick Meals");
});

test("JSON-LD fills optional fields when the data exists", () => {
  const ld = buildJsonLd({ ...base(), servings: 4, cuisine: "French", prep_minutes: 10, cook_minutes: 80, created_at: "2026-03-04T10:00:00Z", hero_image_url: "https://media.cohns.net/images/a.jpg" }, ORIGIN);
  assert.equal(ld.recipeYield, "4 servings");
  assert.equal(ld.prepTime, "PT10M");
  assert.equal(ld.cookTime, "PT1H20M");
  assert.equal(ld.totalTime, "PT1H30M");
  assert.equal(ld.datePublished, "2026-03-04");
  assert.equal(ld.keywords, "Quick Meals, French");
});

test("VideoObject carries thumbnail and content URL, and no guessed uploadDate", () => {
  const v = buildJsonLd({ ...base(), video_key: "lessons/syrup" }, ORIGIN).video;
  assert.equal(v.thumbnailUrl, "https://media.cohns.net/lessons/syrup/thumb/syrup_poster.0000000.jpg");
  assert.equal(v.contentUrl, "https://media.cohns.net/lessons/syrup/hls/syrup.m3u8");
  assert.ok(!("uploadDate" in v));
});

test("isoDuration", () => {
  assert.equal(isoDuration(45), "PT45M");
  assert.equal(isoDuration(120), "PT2H");
  assert.equal(isoDuration(0), null);
  assert.equal(isoDuration("x"), null);
});

test("untrusted text cannot break out of HTML or the JSON-LD script", () => {
  const evil = { ...base(), title: '</title><script>alert(1)</script>', summary: "</script><img src=x onerror=alert(1)>" };
  const html = page(evil);
  assert.ok(!html.includes("<script>alert(1)"));
  assert.ok(!html.includes("<img src=x"));
  const ld = html.match(/<script type="application\/ld\+json">([\s\S]*?)<\/script>/)[1];
  assert.equal(JSON.parse(ld).name, evil.title); // round-trips, so the escaping lost nothing
  assert.ok(!jsonForScript({ a: "</script>" }).includes("</script>"));
});

test("disclosure appears iff an Amazon link is on the page, and the link carries our tag", () => {
  assert.ok(!page(base()).includes(DISCLOSURE));
  const html = page({ ...base(), steps: ["Use a [thermometer](https://www.amazon.com/dp/B0?tag=someone-else-20)."] });
  assert.ok(html.includes(DISCLOSURE));
  assert.ok(html.includes("tag=stevecohnsnet-20") && !html.includes("someone-else-20"));
  assert.ok(html.includes("sponsored"));
});

test("gear renders as affiliate links; the empty slot stays hidden outside review environments", () => {
  const withGear = page({ ...base(), gear: [{ name: "Saucepan", url: "https://www.amazon.com/dp/B1", note: "3 qt" }] });
  assert.ok(withGear.includes("Gear used") && withGear.includes("Saucepan") && withGear.includes(DISCLOSURE));
  assert.match(page(base()), /data-slot="gear" hidden/);
  assert.doesNotMatch(page(base(), { showEmptySlots: true }), /data-slot="gear" hidden/);
});

test("email signup is hidden until wired in prod, and live once an action is given", () => {
  assert.match(page(base()), /data-slot="email-signup" hidden/);
  const wired = page(base(), { signupAction: "https://example.com/subscribe" });
  assert.doesNotMatch(wired, /data-slot="email-signup" hidden/);
  assert.match(wired, /action="https:\/\/example.com\/subscribe"/);
});

test("every page links to /classes/ and canonicalizes to the prod URL", () => {
  const html = page(base());
  assert.ok(html.includes('href="/classes/"'));
  assert.ok(html.includes('<link rel="canonical" href="https://steve.cohns.net/recipes/simple-syrup/">'));
  assert.ok(!html.includes('content="noindex"'));
  assert.ok(page(base(), { noindex: true }).includes('content="noindex"'));
});

test("sitemap lists the public pages and recipes, never /family/", () => {
  const xml = buildSitemap([base()], ORIGIN);
  const locs = [...xml.matchAll(/<loc>([^<]+)/g)].map((m) => m[1]);
  assert.deepEqual(locs, ["/", "/foodie/", "/recipes/", "/recipes/simple-syrup/", "/classes/"].map((p) => ORIGIN + p));
  assert.ok(!xml.includes("family") && !xml.includes("lastmod"));
});

test("robots: Sitemap line only in prod", () => {
  const tracked = "User-agent: *\nDisallow: /family/\n\nSitemap: https://steve.cohns.net/sitemap.xml\n";
  assert.equal(robotsFor("prod", tracked), tracked);
  assert.ok(!robotsFor("dev", tracked).includes("Sitemap"));
  assert.ok(robotsFor("dev", tracked).includes("Disallow: /family/"));
});

test("fillMarked replaces the region and refuses a template without markers", () => {
  assert.equal(fillMarked("a<!--static:x-->old<!--/static:x-->b", "x", "NEW"), "a<!--static:x-->NEW<!--/static:x-->b");
  assert.throws(() => fillMarked("<p>no markers</p>", "x", "NEW"), /markers/);
});

test("groupByCategory orders by the vocabulary and puts unknowns in Other", () => {
  const rs = [{ category: "Desserts" }, { category: "Breads" }, { category: "Gone" }, { category: null }];
  assert.deepEqual(groupByCategory(rs, ["Breads", "Desserts"]).map((g) => g.category), ["Breads", "Desserts", "Other"]);
});

test("mdToText strips markup", () => {
  assert.equal(mdToText("A **bold** [link](https://x.y) and `code`"), "A bold link and code");
});
