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

  // Render Markdown (via md.js) into a new element's innerHTML. Falls back to plain
  // text if md.js didn't load. `block` = true for multi-paragraph content (notes),
  // false for one-line content (summary).
  function mdEl(tag, cls, md, block) {
    var n = document.createElement(tag);
    if (cls) n.className = cls;
    if (window.cohnsMD) n.innerHTML = (block ? window.cohnsMD.render : window.cohnsMD.renderInline)(md);
    else n.textContent = md || "";
    return n;
  }

  // onUnavailable() is called when the HLS manifest can't be loaded — most often
  // because a freshly uploaded lesson is still transcoding (the manifest 403s until
  // the pipeline finishes), so the caller can show a "processing" note.
  function playVideo(video, url, onUnavailable) {
    if (video.canPlayType("application/vnd.apple.mpegurl")) {
      video.src = url; // Safari plays HLS natively
      video.addEventListener("error", function () { if (onUnavailable) onUnavailable(); });
    } else if (window.Hls && window.Hls.isSupported()) {
      var hls = new window.Hls();
      hls.on(window.Hls.Events.ERROR, function (_e, data) {
        if (data && data.fatal) { hls.destroy(); if (onUnavailable) onUnavailable(); }
      });
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
    var kids = [];
    if (r.hero_image_url) {
      kids.push(el("img", { class: "recipe-card-thumb", src: r.hero_image_url, alt: "", loading: "lazy" }));
    }
    kids.push(el("h3", {}, [r.title]));
    kids.push(el("p", {}, [r.summary || ""]));
    return el("a", { class: "recipe-card" + (r.hero_image_url ? " has-thumb" : ""), href: "/recipes/recipe.html?slug=" + encodeURIComponent(r.slug) }, kids);
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
      if (r.hero_image_url) {
        root.appendChild(el("img", {
          class: "recipe-hero", src: r.hero_image_url, alt: r.title, loading: "lazy",
        }));
      }
      if (r.summary) root.appendChild(mdEl("p", "recipe-summary", r.summary, false));
      if (r.notes) root.appendChild(mdEl("div", "recipe-notes", r.notes, true));

      if (r.video_key) {
        var videoWrap = el("div", { class: "recipe-video-wrap" });
        var video = el("video", { class: "recipe-video", controls: "", playsinline: "", preload: "metadata" });
        videoWrap.appendChild(video);
        root.appendChild(videoWrap);
        playVideo(video, hlsUrl(r.video_key), function () {
          videoWrap.innerHTML = "";
          videoWrap.appendChild(el("p", { class: "recipe-video-pending" }, [
            "This lesson video is still processing — check back in a few minutes.",
          ]));
        });
      }

      // Ingredients and steps are one line each — render inline Markdown so they
      // support the same bold/italic/code/links as the description and story.
      if ((r.ingredients || []).length) {
        root.appendChild(el("h2", {}, ["Ingredients"]));
        root.appendChild(el("ul", { class: "ingredients" }, r.ingredients.map(function (i) { return mdEl("li", null, i, false); })));
      }
      if ((r.steps || []).length) {
        root.appendChild(el("h2", {}, ["Method"]));
        root.appendChild(el("ol", { class: "steps" }, r.steps.map(function (s) { return mdEl("li", null, s, false); })));
      }

      // FTC + Amazon Associates: show the required disclosure only on pages that
      // actually carry an Amazon affiliate link.
      var links = root.querySelectorAll("a[href]");
      var hasAmazon = false;
      for (var li = 0; li < links.length; li++) {
        if (window.cohnsMD && window.cohnsMD.isAmazonUrl(links[li].href)) { hasAmazon = true; break; }
      }
      if (hasAmazon) {
        root.appendChild(el("p", { class: "affiliate-disclosure" }, [
          "As an Amazon Associate I earn from qualifying purchases.",
        ]));
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
