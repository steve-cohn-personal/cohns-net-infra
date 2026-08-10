// Recipe admin — a moderators-only page to import, edit, categorize, publish, and
// delete recipes. Talks to the content API's /recipes + /admin/recipes endpoints
// (moderator JWT via cohnsAuth; the API enforces it too). Import fetches a URL's
// schema.org/Recipe JSON-LD server-side and returns an unsaved draft to review.

(function () {
  "use strict";

  var CATEGORY_FALLBACK = ["Breads", "Candy", "Quick Meals", "Appetizers", "Main Courses", "Desserts"];

  function apiBase() {
    var h = location.hostname;
    if (h === "localhost" || h.endsWith(".local")) return "http://localhost:8000";
    if (h === "cohns.net" || h.startsWith("www.") || h.startsWith("steve.")) return "https://api.cohns.net";
    return "https://api." + h;
  }

  function el(tag, attrs, children) {
    var n = document.createElement(tag);
    for (var k in attrs || {}) {
      if (k === "checked") { n.checked = attrs[k]; }
      else if (k === "value") { n.value = attrs[k]; }
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

  async function getCategories() {
    try {
      var c = await authJSON(apiBase() + "/recipes/categories");
      if (Array.isArray(c) && c.length) return c;
    } catch (e) { /* fall through */ }
    return CATEGORY_FALLBACK.slice();
  }

  var lines = function (s) { return (s || "").split("\n").map(function (x) { return x.trim(); }).filter(Boolean); };
  var block = function (a) { return (a || []).join("\n"); };

  // --- editor form ----------------------------------------------------------

  function field(labelText, control) {
    return el("label", { class: "form-row" }, [el("span", {}, [labelText]), control]);
  }

  // A live Markdown preview that mirrors how the recipe page renders `input`'s value.
  // mode: "inline" (summary), "block" (story/notes), "lines-ul"/"lines-ol" (ingredients
  // /steps, one Markdown line per item). Hidden when the field is empty.
  function mdPreview(input, mode) {
    var body = el("div", { class: "md-preview-body" });
    var box = el("div", { class: "md-preview" }, [el("div", { class: "md-preview-label" }, ["Preview"]), body]);

    function lines(v) {
      return v.split("\n").map(function (x) { return x.trim(); }).filter(Boolean);
    }
    function render() {
      var M = window.cohnsMD, v = input.value;
      box.style.display = v.trim() ? "" : "none";
      if (!v.trim()) return;
      if (!M) { body.textContent = v; return; }
      if (mode === "inline") {
        body.innerHTML = M.renderInline(v);
      } else if (mode === "block") {
        body.innerHTML = M.render(v);
      } else {
        var tag = mode === "lines-ol" ? "ol" : "ul";
        body.innerHTML = "<" + tag + ' class="' + (tag === "ol" ? "steps" : "ingredients") + '">' +
          lines(v).map(function (l) { return "<li>" + M.renderInline(l) + "</li>"; }).join("") + "</" + tag + ">";
      }
    }
    input.addEventListener("input", render);
    render();
    return box;
  }

  // Uploads a picked image to S3 via a presigned PUT the API mints, then writes the
  // resulting public URL into the given hero_image_url <input> and shows a preview.
  // Returns a form-row: [file picker + status] with a live thumbnail.
  function imageUploadRow(ctx, urlInput, slugInput) {
    var file = el("input", { type: "file", class: "form-input", accept: "image/jpeg,image/png,image/webp,image/gif" });
    var status = el("span", { class: "form-status" });
    var preview = el("img", { class: "hero-preview", alt: "" });
    function showPreview() {
      if (urlInput.value.trim()) { preview.setAttribute("src", urlInput.value.trim()); preview.style.display = ""; }
      else { preview.removeAttribute("src"); preview.style.display = "none"; }
    }
    showPreview();
    urlInput.addEventListener("input", showPreview);

    file.addEventListener("change", async function () {
      var f = file.files && file.files[0];
      if (!f) return;
      status.textContent = "Uploading…";
      try {
        var presign = await authJSON(apiBase() + "/admin/uploads/presign", {
          method: "POST", headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ kind: "image", content_type: f.type, slug: (slugInput.value || "").trim() || null }),
        });
        // Presigned PUT: send the file bytes with exactly the signed Content-Type and
        // NO auth header (the signature is the authorization).
        var put = await fetch(presign.url, { method: "PUT", mode: "cors", headers: presign.headers, body: f });
        if (!put.ok) throw new Error("upload HTTP " + put.status);
        urlInput.value = presign.public_url;
        showPreview();
        status.textContent = "Uploaded.";
      } catch (err) {
        status.textContent = "Upload failed: " + err.message;
      } finally {
        file.value = "";
      }
    });

    return el("div", { class: "form-row" }, [
      el("span", {}, ["Photo — upload replaces the URL below"]),
      el("div", { class: "hero-upload" }, [file, status, preview]),
    ]);
  }

  // Uploads a lesson video's source to the ingest bucket via a presigned PUT; the
  // media pipeline transcodes it to HLS. The object (and thus the video key) is named
  // after the recipe slug, so a re-upload replaces the lesson. Writes the returned
  // video_key into the given <input>.
  function videoUploadRow(ctx, videoKeyInput, slugInput) {
    var file = el("input", { type: "file", class: "form-input", accept: "video/mp4,video/quicktime,video/webm" });
    var status = el("span", { class: "form-status" });

    file.addEventListener("change", async function () {
      var f = file.files && file.files[0];
      if (!f) return;
      var slug = (slugInput.value || "").trim();
      if (!slug) { status.textContent = "Enter a slug first — the video is named after it."; file.value = ""; return; }
      status.textContent = "Uploading… (large files take a moment)";
      try {
        var presign = await authJSON(apiBase() + "/admin/uploads/presign", {
          method: "POST", headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ kind: "video", content_type: f.type, slug: slug }),
        });
        var put = await fetch(presign.url, { method: "PUT", mode: "cors", headers: presign.headers, body: f });
        if (!put.ok) throw new Error("upload HTTP " + put.status);
        videoKeyInput.value = presign.video_key;
        status.textContent = "Uploaded — transcoding now; the video appears on the recipe in a few minutes.";
      } catch (err) {
        status.textContent = "Upload failed: " + err.message;
      } finally {
        file.value = "";
      }
    });

    return el("div", { class: "form-row" }, [
      el("span", {}, ["Lesson video — upload sets the key below"]),
      el("div", { class: "hero-upload" }, [file, status]),
    ]);
  }

  function categorySelect(categories, selected) {
    var sel = el("select", { class: "form-input", name: "category" });
    sel.appendChild(el("option", { value: "" }, ["— Uncategorized —"]));
    categories.forEach(function (c) {
      sel.appendChild(el("option", Object.assign({ value: c }, c === selected ? { selected: "selected" } : {}), [c]));
    });
    return sel;
  }

  // recipe: an existing recipe or an imported draft; originalSlug: set when editing
  // an existing one (so a slug change updates in place).
  function openEditor(ctx, recipe, originalSlug) {
    recipe = recipe || {};
    var form = el("form", { class: "recipe-form" });
    var status = el("p", { class: "form-status" });

    var f = {
      slug: el("input", { class: "form-input", name: "slug", value: recipe.slug || "", required: "required" }),
      title: el("input", { class: "form-input", name: "title", value: recipe.title || "", required: "required" }),
      category: categorySelect(ctx.categories, recipe.category || ""),
      summary: el("textarea", { class: "form-input", name: "summary", rows: "3" }, [recipe.summary || ""]),
      hero_image_url: el("input", { class: "form-input", name: "hero_image_url", value: recipe.hero_image_url || "" }),
      notes: el("textarea", { class: "form-input", name: "notes", rows: "6" }, [recipe.notes || ""]),
      ingredients: el("textarea", { class: "form-input", name: "ingredients", rows: "8" }, [block(recipe.ingredients)]),
      steps: el("textarea", { class: "form-input", name: "steps", rows: "10" }, [block(recipe.steps)]),
      video_key: el("input", { class: "form-input", name: "video_key", value: recipe.video_key || "" }),
      published: el("input", { type: "checkbox", name: "published", checked: !!recipe.published }),
    };

    form.appendChild(el("h3", {}, [originalSlug ? "Edit recipe" : "New recipe"]));
    form.appendChild(field("Slug", f.slug));
    form.appendChild(field("Title", f.title));
    form.appendChild(field("Category", f.category));
    form.appendChild(field("Summary", f.summary));
    form.appendChild(mdPreview(f.summary, "inline"));
    form.appendChild(imageUploadRow(ctx, f.hero_image_url, f.slug));
    form.appendChild(field("Photo URL", f.hero_image_url));
    form.appendChild(field("Story / notes — Markdown, supports [links](https://…)", f.notes));
    form.appendChild(mdPreview(f.notes, "block"));
    form.appendChild(field("Ingredients (one per line) — Markdown: [text](https://…), **bold**", f.ingredients));
    form.appendChild(mdPreview(f.ingredients, "lines-ul"));
    form.appendChild(field("Steps (one per line) — Markdown supported", f.steps));
    form.appendChild(mdPreview(f.steps, "lines-ol"));
    form.appendChild(videoUploadRow(ctx, f.video_key, f.slug));
    form.appendChild(field("Video key (optional)", f.video_key));
    form.appendChild(el("label", { class: "form-check" }, [f.published, el("span", {}, ["Published"])]));

    var save = el("button", { type: "submit", class: "btn" }, ["Save"]);
    var cancel = el("button", { type: "button", class: "btn btn-plain" }, ["Cancel"]);
    cancel.addEventListener("click", function () { ctx.reload(); });
    form.appendChild(el("div", { class: "form-actions" }, [save, cancel, status]));

    form.addEventListener("submit", async function (e) {
      e.preventDefault();
      var payload = {
        slug: f.slug.value.trim(),
        title: f.title.value.trim(),
        category: f.category.value || null,
        summary: f.summary.value.trim() || null,
        hero_image_url: f.hero_image_url.value.trim() || null,
        notes: f.notes.value.trim() || null,
        ingredients: lines(f.ingredients.value),
        steps: lines(f.steps.value),
        video_key: f.video_key.value.trim() || null,
        published: f.published.checked,
      };
      save.disabled = true;
      status.textContent = "Saving…";
      try {
        if (originalSlug) {
          await authJSON(apiBase() + "/recipes/" + encodeURIComponent(originalSlug), { method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify(payload) });
        } else {
          var r = await window.cohnsAuth.authFetch(apiBase() + "/recipes", { method: "POST", mode: "cors", headers: { "Content-Type": "application/json" }, body: JSON.stringify(payload) });
          if (r.status === 409) {
            await authJSON(apiBase() + "/recipes/" + encodeURIComponent(payload.slug), { method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify(payload) });
          } else if (!r.ok) {
            var d = ""; try { d = (await r.json()).detail || ""; } catch (e2) {}
            throw new Error(d || ("HTTP " + r.status));
          }
        }
        ctx.reload();
      } catch (err) {
        save.disabled = false;
        status.textContent = "Save failed: " + err.message;
      }
    });

    ctx.formArea.innerHTML = "";
    ctx.formArea.appendChild(form);
    ctx.formArea.scrollIntoView({ behavior: "smooth", block: "start" });
  }

  // --- import bar + list ----------------------------------------------------

  function toolbar(ctx) {
    var url = el("input", { class: "form-input", type: "url", placeholder: "https://…/a-recipe" });
    var importBtn = el("button", { type: "button", class: "btn" }, ["Import from URL"]);
    var status = el("span", { class: "form-status" });

    importBtn.addEventListener("click", async function () {
      if (!url.value.trim()) { status.textContent = "Enter a recipe URL."; return; }
      importBtn.disabled = true;
      status.textContent = "Importing…";
      try {
        var draft = await authJSON(apiBase() + "/admin/recipes/import", {
          method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ url: url.value.trim() }),
        });
        status.textContent = "Imported — review, pick a category, and save.";
        openEditor(ctx, draft, null);
      } catch (err) {
        status.textContent = "Import failed: " + err.message;
      } finally {
        importBtn.disabled = false;
      }
    });

    var newBtn = el("button", { type: "button", class: "btn btn-plain" }, ["+ New recipe"]);
    newBtn.addEventListener("click", function () { openEditor(ctx, null, null); });

    return el("div", { class: "recipe-admin-bar" }, [
      el("div", { class: "import-row" }, [url, importBtn]),
      newBtn,
      status,
    ]);
  }

  function recipeRow(ctx, r) {
    var edit = el("button", { class: "authbar-btn" }, ["Edit"]);
    edit.addEventListener("click", function () { openEditor(ctx, r, r.slug); });
    var del = el("button", { class: "authbar-btn" }, ["Delete"]);
    del.addEventListener("click", async function () {
      if (!window.confirm('Delete "' + r.title + '"? This cannot be undone.')) return;
      del.disabled = true; del.textContent = "…";
      try { await authJSON(apiBase() + "/recipes/" + encodeURIComponent(r.slug), { method: "DELETE" }); ctx.reload(); }
      catch (e) { del.disabled = false; del.textContent = "Delete (failed)"; }
    });

    var tr = el("tr");
    tr.appendChild(el("td", {}, [r.title]));
    tr.appendChild(el("td", {}, [r.category || "—"]));
    tr.appendChild(el("td", {}, [r.published ? "published" : "draft"]));
    tr.appendChild(el("td", { class: "admin-actions" }, [edit, del]));
    return tr;
  }

  function renderList(ctx, recipes) {
    ctx.listArea.innerHTML = "";
    if (!recipes.length) { ctx.listArea.appendChild(el("p", { class: "placeholder" }, ["No recipes yet."])); return; }
    var table = el("table", { class: "admin-table" });
    table.appendChild(el("thead", {}, [el("tr", {}, ["Title", "Category", "Status", ""].map(function (h) { return el("th", {}, [h]); }))]));
    var tbody = el("tbody");
    recipes.forEach(function (r) { tbody.appendChild(recipeRow(ctx, r)); });
    table.appendChild(tbody);
    ctx.listArea.appendChild(table);
  }

  async function load() {
    var root = document.getElementById("recipes-admin");
    if (!window.cohnsAuth || !window.cohnsAuth.isSignedIn()) { msg(root, "Sign in to manage recipes."); return; }
    var user = window.cohnsAuth.getUser();
    if (!user || !user.isModerator) { msg(root, "You don't have access to this page."); return; }

    root.innerHTML = "";
    var formArea = el("div", { class: "recipe-form-area" });
    var listArea = el("div", { class: "recipe-admin-list" });
    var categories = await getCategories();
    var ctx = { formArea: formArea, listArea: listArea, categories: categories, reload: load };

    root.appendChild(toolbar(ctx));
    root.appendChild(formArea);
    root.appendChild(listArea);

    try {
      renderList(ctx, await authJSON(apiBase() + "/admin/recipes"));
    } catch (e) {
      msg(listArea, "Couldn't load recipes (" + e.message + ").");
    }
  }

  document.addEventListener("DOMContentLoaded", function () { setTimeout(load, 0); });
})();
