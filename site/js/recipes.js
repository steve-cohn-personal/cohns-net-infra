// Recipes UI. Talks to the content API when it's running; falls back to bundled
// sample content otherwise, so the page is never empty. One file drives both the
// list page and the detail page (?slug=...).

(function () {
  "use strict";

  // Derive the API host from the site host: dev.cohns.net -> api.dev.cohns.net,
  // www/apex -> api.cohns.net, localhost -> local dev server.
  function apiBase() {
    var h = location.hostname;
    if (h === "localhost" || h.endsWith(".local")) return "http://localhost:8000";
    if (h === "cohns.net" || h.startsWith("www.") || h.startsWith("steve.")) return "https://api.cohns.net";
    return "https://api." + h;
  }

  // The media CDN that serves transcoded lesson videos (live/media output).
  var MEDIA_CDN = "https://media.cohns.net";

  function hlsUrl(videoKey) {
    var name = videoKey.split("/").pop();
    return MEDIA_CDN + "/" + videoKey + "/hls/" + name + ".m3u8";
  }

  async function getJSON(url, opts) {
    var r = await fetch(url, opts || {});
    if (!r.ok) throw new Error(r.status);
    return r.json();
  }

  async function listRecipes() {
    try {
      var data = await getJSON(apiBase() + "/recipes", { mode: "cors" });
      if (Array.isArray(data) && data.length) return { data: data, live: true };
    } catch (e) {
      /* API not reachable yet — fall through to sample */
    }
    try {
      return { data: await getJSON("/recipes-sample.json"), live: false };
    } catch (e) {
      return { data: [], live: false };
    }
  }

  async function getRecipe(slug) {
    try {
      return { recipe: await getJSON(apiBase() + "/recipes/" + encodeURIComponent(slug), { mode: "cors" }), live: true };
    } catch (e) {
      var all = await listRecipes();
      return { recipe: all.data.find(function (r) { return r.slug === slug; }) || null, live: false };
    }
  }

  function el(tag, attrs, children) {
    var n = document.createElement(tag);
    for (var k in attrs || {}) n.setAttribute(k, attrs[k]);
    (children || []).forEach(function (c) { n.appendChild(typeof c === "string" ? document.createTextNode(c) : c); });
    return n;
  }

  function playVideo(video, url) {
    if (video.canPlayType("application/vnd.apple.mpegurl")) {
      video.src = url; // Safari plays HLS natively
    } else if (window.Hls && window.Hls.isSupported()) {
      var hls = new window.Hls();
      hls.loadSource(url);
      hls.attachMedia(video);
    } else {
      video.insertAdjacentText("afterend", "Your browser can't play this video.");
    }
  }

  // Falls back to the fixed set if /recipes/categories is unreachable (sample mode).
  var CATEGORY_FALLBACK = ["Breads", "Candy", "Quick Meals", "Appetizers", "Main Courses", "Desserts"];
  var OTHER = "Other";

  async function getCategories() {
    try {
      var c = await getJSON(apiBase() + "/recipes/categories", { mode: "cors" });
      if (Array.isArray(c) && c.length) return c;
    } catch (e) { /* fall through to the fixed set */ }
    return CATEGORY_FALLBACK.slice();
  }

  function currentFilter() { return new URLSearchParams(location.search).get("category"); }
  function setFilter(cat) { history.replaceState(null, "", cat ? "?category=" + encodeURIComponent(cat) : location.pathname); }

  function recipeCard(r) {
    return el("a", { class: "recipe-card", href: "/recipes/recipe.html?slug=" + encodeURIComponent(r.slug) }, [
      el("h3", {}, [r.title]),
      el("p", {}, [r.summary || ""]),
    ]);
  }

  // Bucket recipes by category in the canonical order; unknown/null land in "Other"
  // at the end. Empty categories are dropped.
  function orderedGroups(recipes, categories) {
    var groups = {};
    recipes.forEach(function (r) {
      var key = (r.category && categories.indexOf(r.category) !== -1) ? r.category : OTHER;
      (groups[key] = groups[key] || []).push(r);
    });
    return categories.concat([OTHER])
      .filter(function (c) { return groups[c]; })
      .map(function (c) { return { category: c, recipes: groups[c] }; });
  }

  function renderList(root) {
    Promise.all([listRecipes(), getCategories()]).then(function (out) {
      var res = out[0], categories = out[1];
      root.innerHTML = "";

      if (!res.data.length) {
        root.appendChild(el("p", { class: "placeholder" }, ["No recipes published yet."]));
        return;
      }
      if (!res.live) root.appendChild(el("p", { class: "demo-note" }, ["Preview content — recipes populate from the API once it's running."]));

      var groups = orderedGroups(res.data, categories);
      var present = groups.map(function (g) { return g.category; });
      var active = currentFilter();
      if (active && present.indexOf(active) === -1) active = null; // stale/empty filter → show all

      // Filter chips: All + each category that actually has recipes.
      var bar = el("div", { class: "recipe-filters" });
      function chip(label, value) {
        var b = el("button", { type: "button", class: "chip" + (active === value ? " is-active" : "") }, [label]);
        b.addEventListener("click", function () { setFilter(value); renderList(root); });
        return b;
      }
      bar.appendChild(chip("All", null));
      present.forEach(function (c) { bar.appendChild(chip(c, c)); });
      root.appendChild(bar);

      // Grouped sections, narrowed to the active chip if one is set.
      groups
        .filter(function (g) { return !active || g.category === active; })
        .forEach(function (g) {
          var sec = el("section", { class: "recipe-group" }, [el("h2", {}, [g.category])]);
          var grid = el("div", { class: "recipe-grid" });
          g.recipes.forEach(function (r) { grid.appendChild(recipeCard(r)); });
          sec.appendChild(grid);
          root.appendChild(sec);
        });
    });
  }

  function renderDetail(root) {
    var slug = new URLSearchParams(location.search).get("slug");
    if (!slug) { root.appendChild(el("p", { class: "placeholder" }, ["Recipe not found."])); return; }

    getRecipe(slug).then(function (res) {
      root.innerHTML = "";
      var r = res.recipe;
      if (!r) { root.appendChild(el("p", { class: "placeholder" }, ["Recipe not found."])); return; }

      document.title = r.title + " — cohns.net";
      if (r.category) {
        root.appendChild(el("p", { class: "recipe-category" }, [
          el("a", { href: "/recipes/?category=" + encodeURIComponent(r.category) }, [r.category]),
        ]));
      }
      root.appendChild(el("h1", {}, [r.title]));
      if (r.summary) root.appendChild(el("p", { class: "recipe-summary" }, [r.summary]));

      if (r.video_key) {
        var video = el("video", { class: "recipe-video", controls: "", playsinline: "", preload: "metadata" });
        root.appendChild(video);
        playVideo(video, hlsUrl(r.video_key));
      }

      if ((r.ingredients || []).length) {
        root.appendChild(el("h2", {}, ["Ingredients"]));
        root.appendChild(el("ul", { class: "ingredients" }, r.ingredients.map(function (i) { return el("li", {}, [i]); })));
      }
      if ((r.steps || []).length) {
        root.appendChild(el("h2", {}, ["Method"]));
        root.appendChild(el("ol", { class: "steps" }, r.steps.map(function (s) { return el("li", {}, [s]); })));
      }
    });
  }

  document.addEventListener("DOMContentLoaded", function () {
    var list = document.getElementById("recipe-list");
    var detail = document.getElementById("recipe-detail");
    if (list) renderList(list);
    if (detail) renderDetail(detail);
  });
})();
