// The live dashboard link-outs.
//
// Grafana Cloud refuses to be iframed: public dashboards respond with
// `X-Frame-Options: deny` and CSP `frame-ancestors 'none'`, and Cloud exposes no
// way to change that (allow_embedding is self-hosted-only). So each card LINKS OUT
// to its dashboard in a new tab rather than embedding it. If Grafana ever ships a
// tenant frame-ancestors allowlist, swapping a card back to an <iframe src=...>
// plus re-adding frame-src to the live/site CSP is a small change.
//
// One entry per dashboard, keyed to a `.o11y-frame[data-dash=...]` in the HTML.
// `url` is the matching `*_public_url` output of terraform apply in
// terraform/live/observability. An empty `url` renders a "pending apply"
// placeholder rather than linking nowhere.
const DASHBOARDS = {
  slo: {
    url: 'https://indigomarzipan3418.grafana.net/public-dashboards/fe1e3f72de88459193c4cf4f800641fb',
    eyebrow: 'Live · Grafana Cloud',
    title: 'Availability & Latency — SLO',
    desc: 'Uptime and response time for the public sites, probed every minute from five continents. Public dashboard, no login.',
  },
  aurora: {
    // aurora_cost_public_url output of live/observability (enable_cloudwatch).
    url: 'https://indigomarzipan3418.grafana.net/public-dashboards/3124e5955f5b4556b7e9cd9792a9c2f3',
    eyebrow: 'Live · Grafana Cloud',
    title: 'Aurora Serverless Cost — scale-to-zero',
    desc: 'Database capacity in ACU and estimated $/hour, read from CloudWatch by a keyless assumed role. Idle sits at zero — and so does the bill.',
  },
};

(function () {
  const esc = (s) => s.replace(/[&<>"]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));

  document.querySelectorAll('.o11y-frame[data-dash]').forEach((frame) => {
    const cfg = DASHBOARDS[frame.dataset.dash];
    if (!cfg) return;

    if (!cfg.url) {
      const note = document.createElement('p');
      note.className = 'placeholder o11y-pending';
      note.textContent = 'Dashboard pending apply';
      frame.appendChild(note);
      return;
    }

    // A preview panel, not a dead box: name what's live, then a prominent link out.
    // The whole panel is the click target so it reads as one affordance.
    const card = document.createElement('a');
    card.className = 'o11y-preview';
    card.href = cfg.url;
    card.target = '_blank';
    card.rel = 'noopener';
    card.innerHTML = [
      '<span class="o11y-preview__eyebrow">' + esc(cfg.eyebrow) + '</span>',
      '<span class="o11y-preview__title">' + esc(cfg.title) + '</span>',
      '<span class="o11y-preview__desc">' + esc(cfg.desc) + '</span>',
      '<span class="o11y-preview__cta">Open the live dashboard →</span>',
    ].join('');
    frame.appendChild(card);
  });
})();
