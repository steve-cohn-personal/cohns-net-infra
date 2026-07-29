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

  function renderList(root) {
    listRecipes().then(function (res) {
      root.innerHTML = "";
      if (!res.data.length) {
        root.appendChild(el("p", { class: "placeholder" }, ["No recipes published yet."]));
        return;
      }
      if (!res.live) root.appendChild(el("p", { class: "demo-note" }, ["Preview content — recipes populate from the API once it's running."]));
      var grid = el("div", { class: "recipe-grid" });
      res.data.forEach(function (r) {
        var card = el("a", { class: "recipe-card", href: "/recipes/recipe.html?slug=" + encodeURIComponent(r.slug) }, [
          el("h3", {}, [r.title]),
          el("p", {}, [r.summary || ""]),
        ]);
        grid.appendChild(card);
      });
      root.appendChild(grid);
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
