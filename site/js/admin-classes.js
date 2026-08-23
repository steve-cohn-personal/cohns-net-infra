// Class admin — moderators-only. Create/edit classes, schedule sessions, and view
// signup rosters + class requests. Talks to /admin/classes* (moderator JWT via
// cohnsAuth; the API enforces it too). Reuses the image-upload presign flow for hero
// photos and md.js is available for description authoring on the public side.

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
    for (var k in attrs || {}) {
      if (k === "checked") n.checked = attrs[k];
      else if (k === "value") n.value = attrs[k];
      else n.setAttribute(k, attrs[k]);
    }
    (children || []).forEach(function (c) { if (c != null) n.appendChild(typeof c === "string" ? document.createTextNode(c) : c); });
    return n;
  }

  function msg(root, text) { root.innerHTML = ""; root.appendChild(el("p", { class: "placeholder" }, [text])); }

  async function authJSON(url, opts) {
    var r = await window.cohnsAuth.authFetch(url, Object.assign({ mode: "cors" }, opts || {}));
    if (!r.ok) {
      var detail = ""; try { detail = (await r.json()).detail || ""; } catch (e) {}
      throw new Error(detail || ("HTTP " + r.status));
    }
    return r.status === 204 ? null : r.json();
  }

  function field(labelText, control) { return el("label", { class: "form-row" }, [el("span", {}, [labelText]), control]); }

  // datetime-local <-> ISO (UTC). The picker is wall-clock; store an unambiguous instant.
  function isoToLocalInput(iso) {
    if (!iso) return "";
    var d = new Date(iso), pad = function (n) { return String(n).padStart(2, "0"); };
    return d.getFullYear() + "-" + pad(d.getMonth() + 1) + "-" + pad(d.getDate()) + "T" + pad(d.getHours()) + ":" + pad(d.getMinutes());
  }
  function localInputToIso(v) { return v ? new Date(v).toISOString() : null; }
  function fmtWhen(iso) {
    try { return new Date(iso).toLocaleString(undefined, { month: "short", day: "numeric", year: "numeric", hour: "numeric", minute: "2-digit" }); }
    catch (e) { return iso; }
  }

  // Presigned image upload → writes the media URL into urlInput + shows a preview.
  function imageUploadRow(urlInput) {
    var file = el("input", { type: "file", class: "form-input", accept: "image/jpeg,image/png,image/webp,image/gif" });
    var status = el("span", { class: "form-status" });
    var preview = el("img", { class: "hero-preview" });
    function show() { if (urlInput.value.trim()) { preview.setAttribute("src", urlInput.value.trim()); preview.style.display = ""; } else preview.style.display = "none"; }
    show(); urlInput.addEventListener("input", show);
    file.addEventListener("change", async function () {
      var f = file.files && file.files[0]; if (!f) return;
      status.textContent = "Uploading…";
      try {
        var p = await authJSON(apiBase() + "/admin/uploads/presign", { method: "POST", headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ kind: "image", content_type: f.type, slug: "class" }) });
        var put = await fetch(p.url, { method: "PUT", mode: "cors", headers: p.headers, body: f });
        if (!put.ok) throw new Error("upload HTTP " + put.status);
        urlInput.value = p.public_url; show(); status.textContent = "Uploaded.";
      } catch (e) { status.textContent = "Upload failed: " + e.message; } finally { file.value = ""; }
    });
    return el("div", { class: "form-row" }, [el("span", {}, ["Photo — upload replaces the URL below"]), el("div", { class: "hero-upload" }, [file, status, preview])]);
  }

  // A repeatable name/url/note editor for a class's tools (Amazon affiliate links).
  // Returns a form-row element with a _collect() that yields the [{name,url,note}]
  // array, dropping fully-empty rows. URLs are stored raw — the site tags them.
  function toolsEditor(initial) {
    var rows = el("div", {});
    function addRow(t) {
      t = t || {};
      var name = el("input", { class: "form-input", placeholder: "Name", value: t.name || "" });
      var url = el("input", { class: "form-input", placeholder: "https://amzn.to/…", value: t.url || "" });
      var note = el("input", { class: "form-input", placeholder: "Note (optional)", value: t.note || "" });
      var rm = el("button", { type: "button", class: "authbar-btn" }, ["Remove"]);
      var row = el("div", { class: "tool-edit-row" }, [name, url, note, rm]);
      rm.addEventListener("click", function () { rows.removeChild(row); });
      row._get = function () {
        var n = name.value.trim(), u = url.value.trim();
        if (!n && !u) return null;
        return { name: n, url: u, note: note.value.trim() || null };
      };
      rows.appendChild(row);
    }
    (initial || []).forEach(addRow);
    var add = el("button", { type: "button", class: "btn btn-plain" }, ["+ Add tool"]);
    add.addEventListener("click", function () { addRow(null); });
    var wrap = el("div", { class: "form-row" }, [
      el("span", {}, ["Tools I used (Amazon links — the affiliate tag is added automatically)"]),
      rows, add,
    ]);
    wrap._collect = function () {
      return [].slice.call(rows.children).map(function (r) { return r._get ? r._get() : null; }).filter(Boolean);
    };
    return wrap;
  }

  // --- class editor ---------------------------------------------------------

  function openClassEditor(ctx, cls) {
    cls = cls || {};
    var form = el("form", { class: "recipe-form" });
    var status = el("p", { class: "form-status" });
    var f = {
      slug: el("input", { class: "form-input", name: "slug", value: cls.slug || "", required: "required" }),
      title: el("input", { class: "form-input", name: "title", value: cls.title || "", required: "required" }),
      summary: el("textarea", { class: "form-input", name: "summary", rows: "2" }, [cls.summary || ""]),
      description: el("textarea", { class: "form-input", name: "description", rows: "6" }, [cls.description || ""]),
      hero_image_url: el("input", { class: "form-input", name: "hero_image_url", value: cls.hero_image_url || "" }),
      sort_order: el("input", { class: "form-input", name: "sort_order", type: "number", value: cls.sort_order != null ? cls.sort_order : 0 }),
      published: el("input", { type: "checkbox", name: "published", checked: !!cls.published }),
    };
    form.appendChild(el("h3", {}, [cls.id ? "Edit class" : "New class"]));
    form.appendChild(field("Slug", f.slug));
    form.appendChild(field("Title", f.title));
    form.appendChild(field("Summary (short, Markdown)", f.summary));
    form.appendChild(field("Description (Markdown)", f.description));
    var tools = toolsEditor(cls.tools);
    form.appendChild(tools);
    form.appendChild(imageUploadRow(f.hero_image_url));
    form.appendChild(field("Photo URL", f.hero_image_url));
    form.appendChild(field("Sort order", f.sort_order));
    form.appendChild(el("label", { class: "form-check" }, [f.published, el("span", {}, ["Published"])]));
    var save = el("button", { type: "submit", class: "btn" }, ["Save"]);
    var cancel = el("button", { type: "button", class: "btn btn-plain" }, ["Cancel"]);
    cancel.addEventListener("click", function () { ctx.reload(); });
    form.appendChild(el("div", { class: "form-actions" }, [save, cancel, status]));

    form.addEventListener("submit", async function (e) {
      e.preventDefault();
      var payload = {
        slug: f.slug.value.trim(), title: f.title.value.trim(),
        summary: f.summary.value.trim() || null, description: f.description.value.trim() || null,
        tools: tools._collect(),
        hero_image_url: f.hero_image_url.value.trim() || null,
        sort_order: parseInt(f.sort_order.value, 10) || 0, published: f.published.checked,
      };
      save.disabled = true; status.textContent = "Saving…";
      try {
        if (cls.id) await authJSON(apiBase() + "/admin/classes/" + cls.id, { method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify(payload) });
        else await authJSON(apiBase() + "/admin/classes", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(payload) });
        ctx.reload();
      } catch (err) { save.disabled = false; status.textContent = "Save failed: " + err.message; }
    });
    ctx.panel.innerHTML = ""; ctx.panel.appendChild(form); ctx.panel.scrollIntoView({ behavior: "smooth", block: "start" });
  }

  // --- session manager ------------------------------------------------------

  function sessionForm(ctx, cls, s, done) {
    s = s || {};
    var f = {
      starts_at: el("input", { class: "form-input", type: "datetime-local", value: isoToLocalInput(s.starts_at), required: "required" }),
      duration_minutes: el("input", { class: "form-input", type: "number", min: "1", value: s.duration_minutes != null ? s.duration_minutes : "" }),
      location: el("input", { class: "form-input", value: s.location || "" }),
      capacity: el("input", { class: "form-input", type: "number", min: "1", value: s.capacity != null ? s.capacity : "" }),
      status: el("select", { class: "form-input" }, [el("option", { value: "scheduled" }, ["scheduled"]), el("option", Object.assign({ value: "cancelled" }, s.status === "cancelled" ? { selected: "selected" } : {}), ["cancelled"])]),
    };
    var statusEl = el("p", { class: "form-status" });
    var save = el("button", { type: "submit", class: "btn" }, ["Save session"]);
    var form = el("form", { class: "class-form" }, [
      field("Starts at", f.starts_at), field("Duration (min)", f.duration_minutes),
      field("Location", f.location), field("Capacity (blank = unlimited)", f.capacity),
      field("Status", f.status), el("div", { class: "form-actions" }, [save, statusEl]),
    ]);
    form.addEventListener("submit", async function (e) {
      e.preventDefault(); save.disabled = true; statusEl.textContent = "Saving…";
      var payload = {
        starts_at: localInputToIso(f.starts_at.value),
        duration_minutes: f.duration_minutes.value ? parseInt(f.duration_minutes.value, 10) : null,
        location: f.location.value.trim() || null,
        capacity: f.capacity.value ? parseInt(f.capacity.value, 10) : null,
        status: f.status.value,
      };
      try {
        if (s.id) await authJSON(apiBase() + "/admin/classes/sessions/" + s.id, { method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify(payload) });
        else await authJSON(apiBase() + "/admin/classes/" + cls.id + "/sessions", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(payload) });
        done();
      } catch (err) { save.disabled = false; statusEl.textContent = "Save failed: " + err.message; }
    });
    return form;
  }

  function openSessions(ctx, cls) {
    var panel = ctx.panel; panel.innerHTML = "";
    panel.appendChild(el("h3", {}, ["Sessions — " + cls.title]));
    var list = el("div", {});
    var addHost = el("div", {});
    // Re-fetch after any change so the freshly added/edited/removed session shows —
    // rendering the stale in-memory `cls` here is what made adds look like no-ops.
    async function refresh() {
      try {
        var classes = await authJSON(apiBase() + "/admin/classes");
        var fresh = classes.find(function (x) { return x.id === cls.id; });
        if (fresh) openSessions(ctx, fresh); else ctx.reload();
      } catch (e) { ctx.reload(); }
    }

    (cls.sessions || []).forEach(function (s) {
      var row = el("div", { class: "class-session" });
      row.appendChild(el("p", {}, [
        el("strong", {}, [fmtWhen(s.starts_at)]),
        el("span", { class: "class-session-loc" }, [(s.location ? " · " + s.location : "") + " · " + (s.capacity != null ? (s.spots_left + "/" + s.capacity + " open") : "unlimited") + (s.status === "cancelled" ? " · CANCELLED" : "")]),
      ]));
      var edit = el("button", { class: "authbar-btn" }, ["Edit"]);
      var del = el("button", { class: "authbar-btn" }, ["Delete"]);
      var editHost = el("div", {});
      edit.addEventListener("click", function () { editHost.innerHTML = ""; editHost.appendChild(sessionForm(ctx, cls, s, refresh)); });
      del.addEventListener("click", async function () {
        if (!window.confirm("Delete this session? Signups for it are removed too.")) return;
        try { await authJSON(apiBase() + "/admin/classes/sessions/" + s.id, { method: "DELETE" }); refresh(); } catch (e) { window.alert(e.message); }
      });
      row.appendChild(el("div", { class: "admin-actions" }, [edit, del]));
      row.appendChild(editHost);
      list.appendChild(row);
    });
    if (!(cls.sessions || []).length) list.appendChild(el("p", { class: "placeholder" }, ["No sessions yet."]));

    var addBtn = el("button", { type: "button", class: "btn" }, ["+ Add session"]);
    addBtn.addEventListener("click", function () { addHost.innerHTML = ""; addHost.appendChild(sessionForm(ctx, cls, null, refresh)); });
    var back = el("button", { type: "button", class: "btn btn-plain" }, ["Done"]);
    back.addEventListener("click", function () { ctx.reload(); });

    panel.appendChild(list);
    panel.appendChild(el("div", { class: "form-actions" }, [addBtn, back]));
    panel.appendChild(addHost);
    panel.scrollIntoView({ behavior: "smooth", block: "start" });
  }

  async function openSignups(ctx, cls) {
    var panel = ctx.panel; panel.innerHTML = "";
    panel.appendChild(el("h3", {}, ["Signups — " + cls.title]));
    try {
      var rows = await authJSON(apiBase() + "/admin/classes/" + cls.id + "/signups");
      if (!rows.length) { panel.appendChild(el("p", { class: "placeholder" }, ["No signups yet."])); }
      else {
        var table = el("table", { class: "admin-table" });
        table.appendChild(el("thead", {}, [el("tr", {}, ["Name", "Email", "Party", "Status"].map(function (h) { return el("th", {}, [h]); }))]));
        var tb = el("tbody");
        rows.forEach(function (r) { tb.appendChild(el("tr", {}, [el("td", {}, [r.name]), el("td", {}, [r.email]), el("td", {}, [String(r.party_size)]), el("td", {}, [r.status])])); });
        table.appendChild(tb); panel.appendChild(table);
      }
    } catch (e) { panel.appendChild(el("p", { class: "placeholder" }, ["Couldn't load signups (" + e.message + ")."])); }
    var back = el("button", { type: "button", class: "btn btn-plain" }, ["Done"]);
    back.addEventListener("click", function () { ctx.reload(); });
    panel.appendChild(el("div", { class: "form-actions" }, [back]));
  }

  async function showRequests(ctx) {
    var panel = ctx.panel; panel.innerHTML = "";
    panel.appendChild(el("h3", {}, ["Class requests"]));
    try {
      var rows = await authJSON(apiBase() + "/admin/class-requests");
      if (!rows.length) panel.appendChild(el("p", { class: "placeholder" }, ["No requests yet."]));
      else {
        var table = el("table", { class: "admin-table" });
        table.appendChild(el("thead", {}, [el("tr", {}, ["Name", "Email", "Timeframe", "Message"].map(function (h) { return el("th", {}, [h]); }))]));
        var tb = el("tbody");
        rows.forEach(function (r) { tb.appendChild(el("tr", {}, [el("td", {}, [r.name]), el("td", {}, [r.email]), el("td", {}, [r.preferred_timeframe || "—"]), el("td", {}, [r.message || "—"])])); });
        table.appendChild(tb); panel.appendChild(table);
      }
    } catch (e) { panel.appendChild(el("p", { class: "placeholder" }, ["Couldn't load requests (" + e.message + ")."])); }
    var back = el("button", { type: "button", class: "btn btn-plain" }, ["Done"]);
    back.addEventListener("click", function () { ctx.reload(); });
    panel.appendChild(el("div", { class: "form-actions" }, [back]));
  }

  // --- list + load ----------------------------------------------------------

  function classRow(ctx, c) {
    var edit = el("button", { class: "authbar-btn" }, ["Edit"]);
    edit.addEventListener("click", function () { openClassEditor(ctx, c); });
    var sessions = el("button", { class: "authbar-btn" }, ["Sessions (" + (c.sessions || []).length + ")"]);
    sessions.addEventListener("click", function () { openSessions(ctx, c); });
    var signups = el("button", { class: "authbar-btn" }, ["Signups"]);
    signups.addEventListener("click", function () { openSignups(ctx, c); });
    var del = el("button", { class: "authbar-btn" }, ["Delete"]);
    del.addEventListener("click", async function () {
      if (!window.confirm('Delete "' + c.title + '" and all its sessions/signups?')) return;
      try { await authJSON(apiBase() + "/admin/classes/" + c.id, { method: "DELETE" }); ctx.reload(); } catch (e) { window.alert(e.message); }
    });
    var tr = el("tr");
    tr.appendChild(el("td", {}, [c.title]));
    tr.appendChild(el("td", {}, [c.published ? "published" : "draft"]));
    tr.appendChild(el("td", { class: "admin-actions" }, [edit, sessions, signups, del]));
    return tr;
  }

  async function load() {
    var root = document.getElementById("classes-admin");
    if (!window.cohnsAuth || !window.cohnsAuth.isSignedIn()) { msg(root, "Sign in to manage classes."); return; }
    var user = window.cohnsAuth.getUser();
    if (!user || !user.isModerator) { msg(root, "You don't have access to this page."); return; }

    root.innerHTML = "";
    var panel = el("div", { class: "recipe-form-area" });
    var listArea = el("div", {});
    var ctx = { panel: panel, reload: load };

    var newBtn = el("button", { type: "button", class: "btn" }, ["+ New class"]);
    newBtn.addEventListener("click", function () { openClassEditor(ctx, null); });
    var reqBtn = el("button", { type: "button", class: "btn btn-plain" }, ["View class requests"]);
    reqBtn.addEventListener("click", function () { showRequests(ctx); });
    root.appendChild(el("div", { class: "recipe-admin-bar" }, [newBtn, reqBtn]));
    root.appendChild(panel);
    root.appendChild(listArea);

    try {
      var classes = await authJSON(apiBase() + "/admin/classes");
      if (!classes.length) { listArea.appendChild(el("p", { class: "placeholder" }, ["No classes yet."])); return; }
      var table = el("table", { class: "admin-table" });
      table.appendChild(el("thead", {}, [el("tr", {}, ["Class", "Status", ""].map(function (h) { return el("th", {}, [h]); }))]));
      var tb = el("tbody");
      classes.forEach(function (c) { tb.appendChild(classRow(ctx, c)); });
      table.appendChild(tb); listArea.appendChild(table);
    } catch (e) { msg(listArea, "Couldn't load classes (" + e.message + ")."); }
  }

  document.addEventListener("DOMContentLoaded", function () { setTimeout(load, 0); });
})();
