// Category admin — moderators-only. Add, rename, reorder, and delete the recipe
// categories (the vocabulary in the categories table). Talks to /admin/categories
// (moderator JWT via cohnsAuth; the API enforces it too). New categories append to
// the end; use ↑/↓ to reorder. Deleting a category that recipes still use is blocked
// by the API (409) — reassign those recipes first.

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
      if (k === "disabled") { n.disabled = attrs[k]; }
      else { n.setAttribute(k, attrs[k]); }
    }
    (children || []).forEach(function (c) {
      if (c == null) return;
      n.appendChild(typeof c === "string" ? document.createTextNode(c) : c);
    });
    return n;
  }

  function msg(root, text) {
    root.innerHTML = "";
    root.appendChild(el("p", { class: "placeholder" }, [text]));
  }

  async function authJSON(url, opts) {
    var r = await window.cohnsAuth.authFetch(url, Object.assign({ mode: "cors" }, opts || {}));
    if (!r.ok) {
      var detail = "";
      try { detail = (await r.json()).detail || ""; } catch (e) { /* no body */ }
      throw new Error(detail || ("HTTP " + r.status));
    }
    return r.status === 204 ? null : r.json();
  }

  function put(id, body) {
    return authJSON(apiBase() + "/admin/categories/" + id, {
      method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body),
    });
  }

  function row(ctx, cats, i) {
    var c = cats[i];

    function moveBtn(label, other) {
      var b = el("button", { class: "authbar-btn", disabled: !other }, [label]);
      if (other) {
        b.addEventListener("click", async function () {
          try {
            await put(c.id, { name: c.name, sort_order: other.sort_order });
            await put(other.id, { name: other.name, sort_order: c.sort_order });
            ctx.reload();
          } catch (e) { ctx.status("Reorder failed: " + e.message); }
        });
      }
      return b;
    }

    var rename = el("button", { class: "authbar-btn" }, ["Rename"]);
    rename.addEventListener("click", async function () {
      var name = window.prompt("Rename category (this updates every recipe using it):", c.name);
      if (!name || name.trim() === c.name) return;
      try { await put(c.id, { name: name.trim(), sort_order: c.sort_order }); ctx.reload(); }
      catch (e) { ctx.status("Rename failed: " + e.message); }
    });

    var del = el("button", { class: "authbar-btn" }, ["Delete"]);
    del.addEventListener("click", async function () {
      if (!window.confirm('Delete category "' + c.name + '"?')) return;
      try { await authJSON(apiBase() + "/admin/categories/" + c.id, { method: "DELETE" }); ctx.reload(); }
      catch (e) { ctx.status(e.message); }  // e.g. "…is used by N recipe(s); reassign them first"
    });

    var tr = el("tr");
    tr.appendChild(el("td", {}, [c.name]));
    tr.appendChild(el("td", { class: "admin-actions" }, [
      moveBtn("↑", cats[i - 1]), moveBtn("↓", cats[i + 1]), rename, del,
    ]));
    return tr;
  }

  function render(ctx, cats) {
    ctx.listArea.innerHTML = "";
    if (!cats.length) { ctx.listArea.appendChild(el("p", { class: "placeholder" }, ["No categories yet."])); return; }
    var table = el("table", { class: "admin-table" });
    table.appendChild(el("thead", {}, [el("tr", {}, [el("th", {}, ["Category"]), el("th", {}, ["Order / actions"])])]));
    var tbody = el("tbody");
    cats.forEach(function (_, i) { tbody.appendChild(row(ctx, cats, i)); });
    table.appendChild(tbody);
    ctx.listArea.appendChild(table);
  }

  function addBar(ctx, maxSort) {
    var name = el("input", { class: "form-input", type: "text", placeholder: "New category name" });
    var add = el("button", { type: "button", class: "btn" }, ["Add category"]);
    add.addEventListener("click", async function () {
      if (!name.value.trim()) { ctx.status("Enter a category name."); return; }
      add.disabled = true;
      try {
        await authJSON(apiBase() + "/admin/categories", {
          method: "POST", headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ name: name.value.trim(), sort_order: maxSort + 1 }),
        });
        ctx.reload();
      } catch (e) { ctx.status("Add failed: " + e.message); add.disabled = false; }
    });
    return el("div", { class: "recipe-admin-bar" }, [
      el("div", { class: "import-row" }, [name, add]), ctx.statusEl,
    ]);
  }

  async function load() {
    var root = document.getElementById("categories-admin");
    if (!window.cohnsAuth || !window.cohnsAuth.isSignedIn()) { msg(root, "Sign in to manage categories."); return; }
    var user = window.cohnsAuth.getUser();
    if (!user || !user.isModerator) { msg(root, "You don't have access to this page."); return; }

    root.innerHTML = "";
    var statusEl = el("span", { class: "form-status" });
    var listArea = el("div", {});
    var ctx = { listArea: listArea, statusEl: statusEl, reload: load, status: function (t) { statusEl.textContent = t; } };

    try {
      var cats = await authJSON(apiBase() + "/admin/categories");
      var maxSort = cats.reduce(function (m, c) { return Math.max(m, c.sort_order); }, -1);
      root.appendChild(addBar(ctx, maxSort));
      root.appendChild(listArea);
      render(ctx, cats);
    } catch (e) {
      msg(root, "Couldn't load categories (" + e.message + ").");
    }
  }

  document.addEventListener("DOMContentLoaded", function () { setTimeout(load, 0); });
})();
