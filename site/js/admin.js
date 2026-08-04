// Access admin — a moderators-only page to grant/revoke group membership, so
// approving someone into the family library is a click, not an AWS console trip.
// Talks to the content API's /admin/users endpoints (moderator JWT required; the
// API enforces it too — this just avoids showing a page that would only 403).

(function () {
  "use strict";

  var GROUPS = ["family", "moderators"];

  function apiBase() {
    var h = location.hostname;
    if (h === "localhost" || h.endsWith(".local")) return "http://localhost:8000";
    if (h === "cohns.net" || h.startsWith("www.") || h.startsWith("steve.")) return "https://api.cohns.net";
    return "https://api." + h;
  }

  function el(tag, attrs, children) {
    var n = document.createElement(tag);
    for (var k in attrs || {}) n.setAttribute(k, attrs[k]);
    (children || []).forEach(function (c) {
      n.appendChild(typeof c === "string" ? document.createTextNode(c) : c);
    });
    return n;
  }

  function msg(root, text) {
    root.innerHTML = "";
    root.appendChild(el("p", { class: "placeholder" }, [text]));
  }

  async function fetchUsers() {
    var r = await window.cohnsAuth.authFetch(apiBase() + "/admin/users", { mode: "cors" });
    if (!r.ok) throw new Error("HTTP " + r.status);
    return r.json();
  }

  async function setGroup(username, group, member) {
    var url = apiBase() + "/admin/users/" + encodeURIComponent(username) + "/groups/" + encodeURIComponent(group);
    var r = await window.cohnsAuth.authFetch(url, { method: member ? "PUT" : "DELETE", mode: "cors" });
    if (!r.ok) throw new Error("HTTP " + r.status);
  }

  function groupCell(user, reload) {
    var td = el("td", { class: "admin-actions" });
    GROUPS.forEach(function (g) {
      var inGroup = (user.groups || []).indexOf(g) !== -1;
      var btn = el("button", { class: "authbar-btn" + (inGroup ? " is-on" : "") }, [(inGroup ? "Revoke " : "Grant ") + g]);
      btn.addEventListener("click", async function () {
        btn.disabled = true;
        btn.textContent = "…";
        try {
          await setGroup(user.username, g, !inGroup);
          reload();
        } catch (e) {
          console.error(e);
          btn.disabled = false;
          btn.textContent = (inGroup ? "Revoke " : "Grant ") + g + " (failed)";
        }
      });
      td.appendChild(btn);
    });
    return td;
  }

  function renderTable(root, users, reload) {
    root.innerHTML = "";
    if (!users.length) {
      msg(root, "No users yet.");
      return;
    }
    var table = el("table", { class: "admin-table" });
    table.appendChild(el("thead", {}, [
      el("tr", {}, ["User", "Name", "Status", "Access"].map(function (h) { return el("th", {}, [h]); })),
    ]));
    var tbody = el("tbody");
    users.forEach(function (u) {
      var tr = el("tr");
      tr.appendChild(el("td", {}, [u.email || u.username]));
      tr.appendChild(el("td", {}, [u.name || "—"]));
      tr.appendChild(el("td", {}, [(u.status || "").toLowerCase().replace(/_/g, " ")]));
      tr.appendChild(groupCell(u, reload));
      tbody.appendChild(tr);
    });
    table.appendChild(tbody);
    root.appendChild(table);
  }

  async function load() {
    var root = document.getElementById("admin");

    if (!window.cohnsAuth || !window.cohnsAuth.isSignedIn()) {
      msg(root, "Sign in to manage access.");
      return;
    }
    var user = window.cohnsAuth.getUser();
    if (!user || !user.isModerator) {
      msg(root, "You don't have access to this page.");
      return;
    }
    try {
      renderTable(root, await fetchUsers(), load);
    } catch (e) {
      console.error(e);
      msg(root, "Couldn't load users (" + e.message + ").");
    }
  }

  document.addEventListener("DOMContentLoaded", function () {
    // Give auth.js's DOMContentLoaded handler a tick to process any sign-in redirect.
    setTimeout(load, 0);
  });
})();
