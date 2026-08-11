// Public classes UI. One file drives the list page (#class-list) and the detail
// page (#class-detail, ?slug=…). People sign up for a scheduled session or request a
// class — name + email, no login. Talks to the content API's /classes endpoints.

(function () {
  "use strict";

  function apiBase() {
    var h = location.hostname;
    if (h === "localhost" || h.endsWith(".local")) return "http://localhost:8000";
    if (h === "cohns.net" || h.startsWith("www.") || h.startsWith("steve.")) return "https://api.cohns.net";
    return "https://api." + h;
  }

  function el(tag, attrs, children) {
    var n = document.createElement(tag);
    for (var k in attrs || {}) n.setAttribute(k, attrs[k]);
    (children || []).forEach(function (c) { if (c != null) n.appendChild(typeof c === "string" ? document.createTextNode(c) : c); });
    return n;
  }

  function mdEl(tag, cls, md, block) {
    var n = document.createElement(tag);
    if (cls) n.className = cls;
    if (window.cohnsMD) n.innerHTML = (block ? window.cohnsMD.render : window.cohnsMD.renderInline)(md);
    else n.textContent = md || "";
    return n;
  }

  async function getJSON(url, opts) {
    var r = await fetch(url, opts || {});
    if (!r.ok) throw new Error(r.status);
    return r.json();
  }

  function fmtWhen(iso) {
    try {
      return new Date(iso).toLocaleString(undefined, {
        weekday: "long", month: "long", day: "numeric", hour: "numeric", minute: "2-digit",
      });
    } catch (e) { return iso; }
  }

  function spotsLabel(s) {
    if (s.capacity == null) return "Open";
    if (s.spots_left <= 0) return "Full — join waitlist";
    return s.spots_left + " spot" + (s.spots_left === 1 ? "" : "s") + " left";
  }

  // A small labelled text/textarea field.
  function field(labelText, control) {
    return el("label", { class: "form-row" }, [el("span", {}, [labelText]), control]);
  }
  function input(name, attrs) { return el("input", Object.assign({ class: "form-input", name: name }, attrs || {})); }

  // A hidden honeypot the server drops if filled.
  function honeypot() {
    return el("input", { type: "text", name: "hp", tabindex: "-1", autocomplete: "off",
      style: "position:absolute;left:-9999px", "aria-hidden": "true" });
  }

  async function postForm(url, body, statusEl, okText) {
    statusEl.textContent = "Sending…";
    try {
      var r = await fetch(url, { method: "POST", mode: "cors",
        headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
      if (!r.ok) {
        var d = ""; try { d = (await r.json()).detail || ""; } catch (e) {}
        throw new Error(d || ("HTTP " + r.status));
      }
      var out = await r.json();
      statusEl.className = "form-status is-ok";
      statusEl.textContent = out.status === "waitlisted"
        ? "You're on the waitlist — I'll be in touch if a spot opens."
        : okText;
      return true;
    } catch (e) {
      statusEl.className = "form-status is-err";
      statusEl.textContent = "Sorry, that didn't go through: " + e.message;
      return false;
    }
  }

  // --- list -----------------------------------------------------------------

  function classCard(c) {
    var kids = [];
    if (c.hero_image_url) kids.push(el("img", { class: "recipe-card-thumb", src: c.hero_image_url, alt: "", loading: "lazy" }));
    kids.push(el("h3", {}, [c.title]));
    kids.push(el("p", {}, [c.summary || ""]));
    var n = (c.sessions || []).length;
    kids.push(el("p", { class: "class-card-meta" }, [n ? (n + " upcoming session" + (n === 1 ? "" : "s")) : "Request a date"]));
    return el("a", { class: "recipe-card" + (c.hero_image_url ? " has-thumb" : ""),
      href: "/classes/class.html?slug=" + encodeURIComponent(c.slug) }, kids);
  }

  function renderList(root) {
    getJSON(apiBase() + "/classes", { mode: "cors" }).then(function (classes) {
      root.innerHTML = "";
      if (!classes.length) { root.appendChild(el("p", { class: "placeholder" }, ["No classes posted yet — check back soon."])); return; }
      var grid = el("div", { class: "recipe-grid" });
      classes.forEach(function (c) { grid.appendChild(classCard(c)); });
      root.appendChild(grid);
    }).catch(function () {
      root.innerHTML = "";
      root.appendChild(el("p", { class: "placeholder" }, ["Couldn't load classes right now."]));
    });
  }

  // --- detail ---------------------------------------------------------------

  function signupForm(slug, session) {
    var name = input("name", { required: "required", placeholder: "Your name" });
    var email = input("email", { type: "email", required: "required", placeholder: "you@example.com" });
    var party = input("party_size", { type: "number", min: "1", max: "20", value: "1" });
    var message = el("textarea", { class: "form-input", name: "message", rows: "2", placeholder: "Anything I should know? (optional)" });
    var statusEl = el("p", { class: "form-status" });
    var submit = el("button", { type: "submit", class: "btn" }, ["Sign up"]);
    var form = el("form", { class: "class-form" }, [
      field("Name", name), field("Email", email), field("Party size", party),
      field("Message", message), honeypot(),
      el("div", { class: "form-actions" }, [submit, statusEl]),
    ]);
    form.addEventListener("submit", async function (e) {
      e.preventDefault();
      submit.disabled = true;
      var ok = await postForm(apiBase() + "/classes/" + encodeURIComponent(slug) + "/sessions/" + session.id + "/signup",
        { name: name.value.trim(), email: email.value.trim(), party_size: parseInt(party.value, 10) || 1,
          message: message.value.trim() || null, hp: form.hp.value },
        statusEl, "You're signed up — see you there!");
      if (ok) form.querySelectorAll("input,textarea,button").forEach(function (n) { n.disabled = true; });
      else submit.disabled = false;
    });
    return form;
  }

  function sessionBlock(slug, s) {
    var wrap = el("div", { class: "class-session" });
    wrap.appendChild(el("p", { class: "class-session-when" }, [
      el("strong", {}, [fmtWhen(s.starts_at)]),
      s.location ? el("span", { class: "class-session-loc" }, [" · " + s.location]) : null,
      el("span", { class: "class-session-spots" }, [" · " + spotsLabel(s)]),
    ]));
    var toggle = el("button", { type: "button", class: "btn btn-plain" }, ["Sign up"]);
    var formHost = el("div", {});
    toggle.addEventListener("click", function () {
      if (formHost.firstChild) { formHost.innerHTML = ""; toggle.textContent = "Sign up"; }
      else { formHost.appendChild(signupForm(slug, s)); toggle.textContent = "Close"; }
    });
    wrap.appendChild(toggle);
    wrap.appendChild(formHost);
    return wrap;
  }

  function requestForm(slug) {
    var name = input("name", { required: "required", placeholder: "Your name" });
    var email = input("email", { type: "email", required: "required", placeholder: "you@example.com" });
    var when = input("preferred_timeframe", { placeholder: "Preferred timeframe (optional)" });
    var message = el("textarea", { class: "form-input", name: "message", rows: "2", placeholder: "What are you hoping to learn? (optional)" });
    var statusEl = el("p", { class: "form-status" });
    var submit = el("button", { type: "submit", class: "btn" }, ["Request this class"]);
    var form = el("form", { class: "class-form" }, [
      field("Name", name), field("Email", email), field("Preferred timeframe", when),
      field("Message", message), honeypot(),
      el("div", { class: "form-actions" }, [submit, statusEl]),
    ]);
    form.addEventListener("submit", async function (e) {
      e.preventDefault();
      submit.disabled = true;
      var ok = await postForm(apiBase() + "/classes/" + encodeURIComponent(slug) + "/request",
        { name: name.value.trim(), email: email.value.trim(),
          preferred_timeframe: when.value.trim() || null, message: message.value.trim() || null, hp: form.hp.value },
        statusEl, "Got it — I'll email you when I schedule one.");
      if (ok) form.querySelectorAll("input,textarea,button").forEach(function (n) { n.disabled = true; });
      else submit.disabled = false;
    });
    return form;
  }

  function renderDetail(root) {
    var slug = new URLSearchParams(location.search).get("slug");
    if (!slug) { root.appendChild(el("p", { class: "placeholder" }, ["Class not found."])); return; }

    getJSON(apiBase() + "/classes/" + encodeURIComponent(slug), { mode: "cors" }).then(function (c) {
      root.innerHTML = "";
      document.title = c.title + " — cohns.net";
      root.appendChild(el("h1", {}, [c.title]));
      if (c.hero_image_url) root.appendChild(el("img", { class: "recipe-hero", src: c.hero_image_url, alt: c.title, loading: "lazy" }));
      if (c.summary) root.appendChild(mdEl("p", "recipe-summary", c.summary, false));
      if (c.description) root.appendChild(mdEl("div", "recipe-notes", c.description, true));

      if ((c.sessions || []).length) {
        root.appendChild(el("h2", {}, ["Upcoming sessions"]));
        c.sessions.forEach(function (s) { root.appendChild(sessionBlock(slug, s)); });
      } else {
        root.appendChild(el("p", { class: "class-none" }, ["No dates scheduled right now — request one below and I'll be in touch."]));
      }

      root.appendChild(el("h2", {}, ["Request this class"]));
      root.appendChild(el("p", { class: "class-request-lead" }, ["Want a session, or a different date? Let me know."]));
      root.appendChild(requestForm(slug));
    }).catch(function () {
      root.innerHTML = "";
      root.appendChild(el("p", { class: "placeholder" }, ["Class not found."]));
    });
  }

  document.addEventListener("DOMContentLoaded", function () {
    var list = document.getElementById("class-list");
    var detail = document.getElementById("class-detail");
    if (list) renderList(list);
    if (detail) renderDetail(detail);
  });
})();
