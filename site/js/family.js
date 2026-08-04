// Family photo library UI. Everything here is gated on being signed in AND in the
// Cognito `family` group — the API enforces both; this just renders the states.
//
//   not signed in     -> prompt to sign in (the auth bar has the button)
//   signed in, family  -> thumbnail grid; click a thumb for the full image
//   signed in, not fam -> "invite-only" message (the API returns 403)
//
// Images come back as short-lived S3 presigned URLs from the list endpoint, so the
// bucket is never public and the URLs simply expire.

(function () {
  "use strict";

  // Public API endpoint (not a secret). live/family output: photos_url.
  var PHOTOS_API = "https://soweh7qos7.execute-api.us-west-2.amazonaws.com/photos";

  function el(tag, attrs, children) {
    var n = document.createElement(tag);
    for (var k in attrs || {}) n.setAttribute(k, attrs[k]);
    (children || []).forEach(function (c) {
      n.appendChild(typeof c === "string" ? document.createTextNode(c) : c);
    });
    return n;
  }

  function message(root, text) {
    root.innerHTML = "";
    root.appendChild(el("p", { class: "placeholder" }, [text]));
  }

  function openLightbox(fullUrl, caption) {
    var box = document.getElementById("lightbox");
    var img = box.querySelector("img");
    img.src = fullUrl;
    img.alt = caption || "";
    box.hidden = false;
  }

  function wireLightbox() {
    var box = document.getElementById("lightbox");
    function close() { box.hidden = true; box.querySelector("img").src = ""; }
    box.querySelector(".lightbox-close").addEventListener("click", close);
    box.addEventListener("click", function (e) { if (e.target === box) close(); });
    document.addEventListener("keydown", function (e) { if (e.key === "Escape") close(); });
  }

  function renderGrid(root, photos) {
    root.innerHTML = "";
    if (!photos.length) {
      root.appendChild(el("p", { class: "placeholder" }, ["No photos in the library yet."]));
      return;
    }
    var grid = el("div", { class: "photo-grid" });
    photos.forEach(function (p) {
      var img = el("img", { src: p.thumb, alt: p.caption || "", loading: "lazy" });
      var fig = el("figure", { class: "photo", tabindex: "0", role: "button" });
      fig.appendChild(img);
      if (p.caption) fig.appendChild(el("figcaption", {}, [p.caption]));
      function open() { openLightbox(p.full, p.caption); }
      fig.addEventListener("click", open);
      fig.addEventListener("keydown", function (e) {
        if (e.key === "Enter" || e.key === " ") { e.preventDefault(); open(); }
      });
      grid.appendChild(fig);
    });
    root.appendChild(grid);
  }

  // The content API (comments-api) that handles access requests — same host
  // derivation the recipes page uses. Distinct from PHOTOS_API above.
  function apiBase() {
    var h = location.hostname;
    if (h === "localhost" || h.endsWith(".local")) return "http://localhost:8000";
    if (h === "cohns.net" || h.startsWith("www.") || h.startsWith("steve.")) return "https://api.cohns.net";
    return "https://api." + h;
  }

  // Signed in but not yet in the family group: offer a real request, not a dead end.
  function renderRequestAccess(root) {
    root.innerHTML = "";
    var box = el("div", { class: "placeholder" });
    box.appendChild(el("p", {}, [
      "This is a private family library. Request access and you'll get an email once you're approved — then sign out and back in to view it.",
    ]));
    var btn = el("button", { class: "authbar-btn" }, ["Request access"]);
    btn.addEventListener("click", async function () {
      btn.disabled = true;
      btn.textContent = "Requesting…";
      try {
        var r = await window.cohnsAuth.authFetch(apiBase() + "/access-requests", {
          method: "POST",
          mode: "cors",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ group: "family" }),
        });
        if (!r.ok) throw new Error("HTTP " + r.status);
        message(root, "Thanks — your request is in. You'll get an email once you're approved; then sign out and back in to see the library.");
      } catch (e) {
        console.error(e);
        btn.disabled = false;
        btn.textContent = "Request access";
        box.appendChild(el("p", {}, ["Couldn't send the request just now. Please try again."]));
      }
    });
    box.appendChild(btn);
    root.appendChild(box);
  }

  async function load() {
    var root = document.getElementById("gallery");

    if (!window.cohnsAuth || !window.cohnsAuth.isSignedIn()) {
      message(root, "Sign in to view the family library.");
      return;
    }

    try {
      var res = await window.cohnsAuth.authFetch(PHOTOS_API, { mode: "cors" });
      if (res.status === 403) {
        renderRequestAccess(root);
        return;
      }
      if (res.status === 401) {
        message(root, "Your session expired. Please sign in again.");
        return;
      }
      if (!res.ok) throw new Error("HTTP " + res.status);
      var data = await res.json();
      renderGrid(root, data.photos || []);
    } catch (e) {
      console.error(e);
      message(root, "Couldn't load the library. Please try again.");
    }
  }

  document.addEventListener("DOMContentLoaded", function () {
    wireLightbox();
    // auth.js also listens on DOMContentLoaded to process any sign-in redirect and
    // render the bar; the signed-in check here reads localStorage synchronously, so
    // ordering doesn't matter. Give the redirect handler a tick before we fetch.
    setTimeout(load, 0);
  });
})();
