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

  // --- ingredient scaling ----------------------------------------------------
  // Scale the leading quantity of an ingredient line by a factor so a reader can
  // cook a different number of servings. Only the amount at the start of the line
  // is touched (the common case: "500g carrot", "1 tbsp salt", "1/2 cup rice"),
  // which keeps stray numbers in the text — pan sizes, temperatures — untouched.

  var VULGAR = {
    "¼": 0.25, "½": 0.5, "¾": 0.75, "⅓": 1 / 3, "⅔": 2 / 3,
    "⅛": 0.125, "⅜": 0.375, "⅝": 0.625, "⅞": 0.875,
    "⅕": 0.2, "⅖": 0.4, "⅗": 0.6, "⅘": 0.8, "⅙": 1 / 6, "⅚": 5 / 6,
  };
  var VG = "¼½¾⅓⅔⅛⅜⅝⅞⅕⅖⅗⅘⅙⅚";
  // One quantity token: mixed ("2 1/2"), fraction ("1/2"), decimal/int with an
  // optional trailing vulgar glyph ("2", "2.5", "2½"), or a lone vulgar glyph ("½").
  // The trailing vulgar glyph (and the space before it) is optional as a *unit* — so
  // "2 ½" is one token but "4 " (number then a word) leaves its space for the unit/name.
  var QTY = "(?:\\d+\\s+\\d+\\s*/\\s*\\d+|\\d+\\s*/\\s*\\d+|\\d+(?:\\.\\d+)?(?:\\s*[" + VG + "])?|[" + VG + "])";

  // Friendly kitchen fractions to snap a scaled amount to before falling back to a
  // rounded decimal. Ordered largest-denominator-error-tolerant last isn't needed —
  // we pick the closest.
  var NICE = [[1, 4], [1, 3], [1, 2], [2, 3], [3, 4], [1, 8], [3, 8], [5, 8], [7, 8]];

  function qtyToNumber(token) {
    token = token.trim();
    // Trailing (or lone) vulgar glyph, with an optional whole part: "2½", "½".
    var vg = token.match(new RegExp("^(\\d+)?\\s*([" + VG + "])$"));
    if (vg) return (vg[1] ? parseInt(vg[1], 10) : 0) + VULGAR[vg[2]];
    // ASCII fraction, optionally mixed: "1/2", "2 1/2".
    var fr = token.match(/^(?:(\d+)\s+)?(\d+)\s*\/\s*(\d+)$/);
    if (fr) return (fr[1] ? parseInt(fr[1], 10) : 0) + parseInt(fr[2], 10) / parseInt(fr[3], 10);
    var n = parseFloat(token);
    return isNaN(n) ? null : n;
  }

  function numberToQty(n) {
    if (n == null || !isFinite(n) || n <= 0) return "0";
    var whole = Math.floor(n + 1e-6);
    var frac = n - whole;
    if (frac < 0.02) return String(whole);
    // Snap the fractional part to the closest nice fraction if it's close enough.
    var best = null;
    NICE.forEach(function (f) {
      var err = Math.abs(frac - f[0] / f[1]);
      if (err <= 0.04 && (!best || err < best.err)) best = { num: f[0], den: f[1], err: err };
    });
    if (best) {
      var f = best.num + "/" + best.den;
      return whole ? whole + " " + f : f;
    }
    // No clean fraction — a trimmed 2-decimal number reads fine ("1.75", "2.4").
    return String(Math.round(n * 100) / 100);
  }

  // Scale one ingredient line's leading amount (or leading range, "1-2 onions").
  function scaleIngredient(line, factor) {
    if (factor === 1) return line;
    var re = new RegExp("^(\\s*)(" + QTY + ")(?:(\\s*(?:-|–|—|to)\\s*)(" + QTY + "))?");
    return line.replace(re, function (m, lead, a, sep, b) {
      var av = qtyToNumber(a);
      if (av == null) return m; // shouldn't happen, but never mangle on a parse miss
      var out = lead + numberToQty(av * factor);
      if (b) {
        var bv = qtyToNumber(b);
        out += sep + (bv == null ? b : numberToQty(bv * factor));
      }
      return out;
    });
  }

  // A servings stepper: −/+ buttons around an editable count, plus a "reset" that
  // appears once the reader has scaled away from the recipe's original yield. Calls
  // onChange(current) whenever the count changes so the caller can rescale.
  function servingsControl(base, onChange) {
    var current = base;
    var input = el("input", { class: "form-input servings-input", type: "number", min: "1", max: "1000", value: String(base) });
    var reset = el("button", { type: "button", class: "servings-reset" }, ["reset"]);

    function set(n) {
      n = Math.max(1, Math.min(1000, Math.round(n) || 1));
      current = n;
      input.value = String(n);
      reset.style.display = n === base ? "none" : "";
      onChange(n);
    }
    var minus = el("button", { type: "button", class: "servings-step", "aria-label": "Fewer servings" }, ["−"]);
    var plus = el("button", { type: "button", class: "servings-step", "aria-label": "More servings" }, ["+"]);
    minus.addEventListener("click", function () { set(current - 1); });
    plus.addEventListener("click", function () { set(current + 1); });
    input.addEventListener("change", function () { set(parseInt(input.value, 10)); });
    reset.addEventListener("click", function () { set(base); });
    reset.style.display = "none";

    return el("div", { class: "servings-control" }, [
      el("span", { class: "servings-label" }, ["Servings"]),
      el("div", { class: "servings-stepper" }, [minus, input, plus]),
      reset,
    ]);
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

  async function getCuisines() {
    try {
      var c = await getJSON(apiBase() + "/recipes/cuisines", { mode: "cors" });
      if (Array.isArray(c)) return c;
    } catch (e) { /* sample mode — derive from the recipes themselves below */ }
    return null;
  }

  var DIFFICULTIES = ["Easy", "Medium", "Hard"];

  // Does a recipe match the free-text query across its searchable fields?
  function matchesQuery(r, q) {
    if (!q) return true;
    var hay = [r.title, r.summary, r.notes, (r.ingredients || []).join(" "), (r.steps || []).join(" ")]
      .join(" ").toLowerCase();
    return hay.indexOf(q) !== -1;
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
    Promise.all([listRecipes(), getCategories(), getCuisines()]).then(function (out) {
      var res = out[0], categories = out[1];
      // Cuisines: the API list if reachable, else derive from the recipes on hand.
      var cuisines = out[2];
      if (!cuisines) {
        var seen = {};
        res.data.forEach(function (r) { if (r.cuisine) seen[r.cuisine] = true; });
        cuisines = Object.keys(seen).sort();
      }
      root.innerHTML = "";

      if (!res.data.length) {
        root.appendChild(el("p", { class: "placeholder" }, ["No recipes published yet."]));
        return;
      }
      if (!res.live) root.appendChild(el("p", { class: "demo-note" }, ["Preview content — recipes populate from the API once it's running."]));

      // Filter state, seeded from the URL so cuisine meta-links and shared searches work.
      var params = new URLSearchParams(location.search);
      var state = {
        q: (params.get("q") || "").toLowerCase(),
        category: params.get("category"),
        cuisine: params.get("cuisine") || "",
        difficulty: params.get("difficulty") || "",
      };

      // --- controls: search box, category chips, cuisine + difficulty selects ---
      var search = el("input", { class: "form-input recipe-search", type: "search", placeholder: "Search recipes…", value: params.get("q") || "" });
      search.addEventListener("input", function () { state.q = search.value.trim().toLowerCase(); paint(); });

      var chipBar = el("div", { class: "recipe-filters" });
      var results = el("div", { class: "recipe-results" });

      function selectFacet(placeholder, options, key) {
        var sel = el("select", { class: "form-input recipe-facet" });
        sel.appendChild(el("option", { value: "" }, [placeholder]));
        options.forEach(function (o) { sel.appendChild(el("option", { value: o }, [o])); });
        sel.value = state[key] || "";
        sel.addEventListener("change", function () { state[key] = sel.value; paint(); });
        return sel;
      }
      var facetBar = el("div", { class: "recipe-facets" }, [
        selectFacet("Any cuisine", cuisines, "cuisine"),
        selectFacet("Any difficulty", DIFFICULTIES, "difficulty"),
      ]);

      root.appendChild(el("div", { class: "recipe-controls" }, [search, facetBar]));
      root.appendChild(chipBar);
      root.appendChild(results);

      function apply() {
        return res.data.filter(function (r) {
          return matchesQuery(r, state.q)
            && (!state.category || r.category === state.category)
            && (!state.cuisine || r.cuisine === state.cuisine)
            && (!state.difficulty || r.difficulty === state.difficulty);
        });
      }

      function paint() {
        // Category chips reflect what's present after the *other* filters are applied.
        var forChips = res.data.filter(function (r) {
          return matchesQuery(r, state.q)
            && (!state.cuisine || r.cuisine === state.cuisine)
            && (!state.difficulty || r.difficulty === state.difficulty);
        });
        var present = orderedGroups(forChips, categories).map(function (g) { return g.category; });
        if (state.category && present.indexOf(state.category) === -1) state.category = null;

        chipBar.innerHTML = "";
        function chip(label, value) {
          var b = el("button", { type: "button", class: "chip" + (state.category === value ? " is-active" : "") }, [label]);
          b.addEventListener("click", function () { state.category = value; setFilter(value); paint(); });
          return b;
        }
        chipBar.appendChild(chip("All", null));
        present.forEach(function (c) { if (c !== OTHER) chipBar.appendChild(chip(c, c)); });

        results.innerHTML = "";
        var filtered = apply();
        var searching = state.q || state.cuisine || state.difficulty;

        if (!filtered.length) {
          results.appendChild(el("p", { class: "placeholder" }, ["No recipes match your search."]));
          return;
        }
        if (searching) {
          // Flat result grid when any search/facet is active.
          results.appendChild(el("p", { class: "recipe-result-count" },
            [filtered.length + (filtered.length === 1 ? " recipe" : " recipes")]));
          var grid = el("div", { class: "recipe-grid" });
          filtered.forEach(function (r) { grid.appendChild(recipeCard(r)); });
          results.appendChild(grid);
        } else {
          // Default: grouped by category (narrowed to the active category chip if set).
          orderedGroups(filtered, categories)
            .filter(function (g) { return !state.category || g.category === state.category; })
            .forEach(function (g) {
              var sec = el("section", { class: "recipe-group" }, [el("h2", {}, [g.category])]);
              var grid = el("div", { class: "recipe-grid" });
              g.recipes.forEach(function (r) { grid.appendChild(recipeCard(r)); });
              sec.appendChild(grid);
              results.appendChild(sec);
            });
        }
      }

      paint();
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
      // Cuisine + difficulty meta (each links back to a filtered list; difficulty is
      // just a tag). Rendered only when present.
      var meta = [];
      if (r.cuisine) meta.push(el("a", { class: "recipe-tag", href: "/recipes/?cuisine=" + encodeURIComponent(r.cuisine) }, [r.cuisine]));
      if (r.difficulty) meta.push(el("span", { class: "recipe-tag recipe-tag--plain" }, [r.difficulty]));
      if (meta.length) root.appendChild(el("p", { class: "recipe-meta" }, meta));
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
        var base = Math.max(1, parseInt(r.servings, 10) || 1);
        var list = el("ul", { class: "ingredients" });
        // Repaint every ingredient at `current` servings, scaling the leading amount.
        function paintIngredients(current) {
          var factor = current / base;
          list.innerHTML = "";
          r.ingredients.forEach(function (i) {
            list.appendChild(mdEl("li", null, scaleIngredient(i, factor), false));
          });
        }
        root.appendChild(servingsControl(base, paintIngredients));
        root.appendChild(list);
        paintIngredients(base);
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
