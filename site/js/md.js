// A tiny Markdown-subset renderer, dependency-free and XSS-safe.
//
// Safety: the input is HTML-escaped FIRST, then only a fixed whitelist of tags is
// emitted (p, br, strong, em, code, a, ul/ol/li, h3/h4) with a fixed set of
// attributes (href/target/rel). There is no raw-HTML passthrough, so no sanitizer
// is needed. Link URLs are validated — only http(s), mailto, root-relative, and
// anchors are linked; anything else (javascript:, data:) renders as plain text.
// External links get target="_blank" rel="noopener nofollow sponsored" — "sponsored"
// is the correct signal for affiliate/paid links (e.g. Amazon Associates).
//
// Exposes window.cohnsMD.render(md) for block content (the recipe "story"/notes) and
// window.cohnsMD.renderInline(md) for one-line content (the summary). Output is HTML
// meant for innerHTML.
(function () {
  "use strict";

  function escapeHtml(s) {
    return String(s == null ? "" : s).replace(/[&<>"]/g, function (c) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c];
    });
  }

  var SITE_HOST = /(^|\.)cohns\.net$/i;

  function isSafeUrl(u) {
    return /^(https?:)?\/\//i.test(u) || /^(mailto:|\/|#)/i.test(u);
  }

  function isExternal(u) {
    // Only absolute or protocol-relative URLs can point off-site. Root-relative
    // (/…), anchors (#…) and mailto: are same-site/non-navigational by definition,
    // so they never get target=_blank/sponsored regardless of the serving host.
    if (!/^(https?:)?\/\//i.test(u)) return false;
    try {
      var url = new URL(u.replace(/&amp;/g, "&"), location.origin);
      return !!url.host && !SITE_HOST.test(url.host);
    } catch (e) {
      return false;
    }
  }

  // text and url are already HTML-escaped substrings of the escaped input.
  function link(text, url) {
    if (!isSafeUrl(url)) return text; // unsafe scheme → drop the link, keep the text
    var rel = isExternal(url) ? ' target="_blank" rel="noopener nofollow sponsored"' : "";
    return '<a href="' + url + '"' + rel + ">" + text + "</a>";
  }

  function inline(s) {
    s = s.replace(/\[([^\]]+)\]\(([^)\s]+)\)/g, function (_, t, u) { return link(t, u); });
    s = s.replace(/`([^`]+)`/g, "<code>$1</code>");
    s = s.replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>");
    s = s.replace(/(^|[^*])\*(?!\s)([^*]+?)\*/g, "$1<em>$2</em>");
    s = s.replace(/(^|[^\w])_([^_\s][^_]*?)_(?![\w])/g, "$1<em>$2</em>");
    return s;
  }

  function renderInline(md) {
    if (!md) return "";
    return inline(escapeHtml(md).replace(/\s*\n+\s*/g, " ")).trim();
  }

  function render(md) {
    if (!md) return "";
    return escapeHtml(md).split(/\n\s*\n/).map(function (block) {
      var lines = block.split("\n").filter(function (l) { return l.trim() !== ""; });
      if (!lines.length) return "";
      if (lines.every(function (l) { return /^\s*[-*]\s+/.test(l); })) {
        return "<ul>" + lines.map(function (l) { return "<li>" + inline(l.replace(/^\s*[-*]\s+/, "")) + "</li>"; }).join("") + "</ul>";
      }
      if (lines.every(function (l) { return /^\s*\d+\.\s+/.test(l); })) {
        return "<ol>" + lines.map(function (l) { return "<li>" + inline(l.replace(/^\s*\d+\.\s+/, "")) + "</li>"; }).join("") + "</ol>";
      }
      var h = lines.length === 1 && lines[0].match(/^(#{2,3})\s+(.*)$/);
      if (h) {
        var level = h[1].length + 1; // ## -> h3, ### -> h4
        return "<h" + level + ">" + inline(h[2]) + "</h" + level + ">";
      }
      return "<p>" + lines.map(inline).join("<br>") + "</p>";
    }).join("");
  }

  window.cohnsMD = { render: render, renderInline: renderInline };
})();
