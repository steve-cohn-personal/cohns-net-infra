// Résumé UI. One structured-data file (/resume.json) drives both the rendered page
// and its schema.org/Person JSON-LD. Sections render only when they hold data, so an
// empty work[] / education[] simply doesn't appear — no fabricated placeholders.

(function () {
  "use strict";

  function el(tag, attrs, children) {
    var n = document.createElement(tag);
    for (var k in attrs || {}) {
      if (k === "html") n.innerHTML = attrs[k];
      else n.setAttribute(k, attrs[k]);
    }
    (children || []).forEach(function (c) {
      if (c == null) return;
      n.appendChild(typeof c === "string" ? document.createTextNode(c) : c);
    });
    return n;
  }

  function section(title, nodes) {
    return el("section", { class: "resume-section" }, [el("h2", {}, [title])].concat(nodes));
  }

  function nonEmpty(a) { return Array.isArray(a) && a.length > 0; }

  function contactLinks(basics) {
    var links = [];
    if (basics.email) links.push(el("a", { href: "mailto:" + basics.email }, [basics.email]));
    (basics.profiles || []).forEach(function (p) {
      links.push(el("a", { href: p.url, rel: "me noopener", target: "_blank" }, [p.network]));
    });
    return links;
  }

  function renderHead(basics) {
    return el("header", { class: "resume-head" }, [
      el("p", { class: "resume-name" }, [basics.name]),
      el("p", { class: "resume-label" }, [
        [basics.label, basics.location].filter(Boolean).join("  ·  "),
      ]),
      el("p", { class: "resume-contact" }, contactLinks(basics)),
    ]);
  }

  function renderSkills(skills) {
    var ul = el("ul", { class: "skills" }, skills.map(function (s) {
      return el("li", {}, [el("span", {}, [s.category]), document.createTextNode(" " + s.items)]);
    }));
    return section("Skills", [ul]);
  }

  function renderProjects(projects) {
    var items = projects.map(function (p) {
      var head = p.url
        ? el("h3", {}, [el("a", { href: p.url, rel: "noopener", target: "_blank" }, [p.name])])
        : el("h3", {}, [p.name]);
      var nodes = [head];
      if (p.summary) nodes.push(el("p", { class: "resume-project-summary" }, [p.summary]));
      if (nonEmpty(p.highlights)) {
        nodes.push(el("ul", { class: "resume-highlights" }, p.highlights.map(function (h) {
          return el("li", {}, [h]);
        })));
      }
      return el("div", { class: "resume-project" }, nodes);
    });
    return section("Selected work", items);
  }

  function fmtDates(w) {
    var span = [w.startDate, w.endDate || (w.startDate ? "Present" : null)].filter(Boolean).join(" – ");
    return span || null;
  }

  function renderExperience(work) {
    var items = work.map(function (w) {
      var title = [w.position, w.company || w.name].filter(Boolean).join(", ");
      var nodes = [
        el("div", { class: "resume-role-head" }, [
          el("h3", {}, [title]),
          el("span", { class: "resume-dates" }, [fmtDates(w)]),
        ]),
      ];
      if (w.summary) nodes.push(el("p", {}, [w.summary]));
      if (nonEmpty(w.highlights)) {
        nodes.push(el("ul", { class: "resume-highlights" }, w.highlights.map(function (h) {
          return el("li", {}, [h]);
        })));
      }
      return el("div", { class: "resume-role" }, nodes);
    });
    return section("Experience", items);
  }

  function renderEducation(education) {
    var items = education.map(function (e) {
      var title = [e.studyType, e.area].filter(Boolean).join(", ") || e.institution;
      return el("div", { class: "resume-role" }, [
        el("div", { class: "resume-role-head" }, [
          el("h3", {}, [title]),
          el("span", { class: "resume-dates" }, [fmtDates(e)]),
        ]),
        e.institution && title !== e.institution ? el("p", {}, [e.institution]) : null,
      ]);
    });
    return section("Education", items);
  }

  // schema.org/Person, generated from the same data — machine-readable résumé.
  function injectJsonLd(basics) {
    var person = {
      "@context": "https://schema.org",
      "@type": "Person",
      name: basics.name,
      jobTitle: basics.label,
      email: basics.email ? "mailto:" + basics.email : undefined,
      url: basics.url,
      address: basics.location ? { "@type": "PostalAddress", addressLocality: basics.location } : undefined,
      sameAs: (basics.profiles || []).map(function (p) { return p.url; }),
    };
    var s = document.createElement("script");
    s.type = "application/ld+json";
    s.textContent = JSON.stringify(person);
    document.head.appendChild(s);
  }

  function render(root, data) {
    var basics = data.basics || {};
    root.innerHTML = "";
    root.appendChild(renderHead(basics));
    if (basics.summary) root.appendChild(el("p", { class: "resume-summary" }, [basics.summary]));
    if (nonEmpty(data.skills)) root.appendChild(renderSkills(data.skills));
    if (nonEmpty(data.projects)) root.appendChild(renderProjects(data.projects));
    if (nonEmpty(data.work)) root.appendChild(renderExperience(data.work));
    if (nonEmpty(data.education)) root.appendChild(renderEducation(data.education));
    injectJsonLd(basics);
  }

  document.addEventListener("DOMContentLoaded", function () {
    var root = document.getElementById("resume");
    if (!root) return;

    var printBtn = document.getElementById("resume-print");
    if (printBtn) printBtn.addEventListener("click", function () { window.print(); });

    fetch("/resume.json")
      .then(function (r) { if (!r.ok) throw new Error(r.status); return r.json(); })
      .then(function (data) { render(root, data); })
      .catch(function () {
        root.innerHTML = "";
        root.appendChild(el("p", { class: "placeholder" }, ["Résumé is unavailable right now."]));
      });
  });
})();
