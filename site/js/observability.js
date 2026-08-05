// The live dashboard link-out.
//
// Grafana Cloud refuses to be iframed: the public dashboard responds with
// `X-Frame-Options: deny` and CSP `frame-ancestors 'none'`, and Cloud exposes no
// way to change that (it is self-hosted-only via allow_embedding). So this renders
// a preview card that links out to the dashboard in a new tab rather than an
// embed. If Grafana ever adds a tenant frame-ancestors allowlist, swapping back to
// an <iframe src=...> here plus re-adding frame-src to the live/site CSP is a
// small change.
//
// URL is the `slo_public_url` output of terraform apply in
// terraform/live/observability. Left empty, the card reads "pending apply" rather
// than linking nowhere.
const PUBLIC_DASHBOARD_URL = 'https://indigomarzipan3418.grafana.net/public-dashboards/fe1e3f72de88459193c4cf4f800641fb';

(function () {
  const frame = document.querySelector('.o11y-frame');
  const link = document.getElementById('o11y-live');
  if (!frame) return;

  if (!PUBLIC_DASHBOARD_URL) {
    const note = document.createElement('p');
    note.className = 'placeholder o11y-pending';
    note.textContent = 'Dashboard pending apply';
    frame.appendChild(note);
    if (link) link.hidden = true;
    return;
  }

  // A preview panel, not a dead box: name what's live, then a prominent link out.
  // The whole panel is the click target so it reads as one affordance.
  const card = document.createElement('a');
  card.className = 'o11y-preview';
  card.href = PUBLIC_DASHBOARD_URL;
  card.target = '_blank';
  card.rel = 'noopener';
  card.innerHTML = [
    '<span class="o11y-preview__eyebrow">Live · Grafana Cloud</span>',
    '<span class="o11y-preview__title">Availability &amp; Latency — SLO</span>',
    '<span class="o11y-preview__desc">Uptime and response time for the public sites, ' +
      'probed every minute from five continents. Public dashboard, no login.</span>',
    '<span class="o11y-preview__cta">Open the live dashboard →</span>',
  ].join('');
  frame.appendChild(card);

  // The whole panel links out, so the separate text link below is redundant.
  if (link && link.parentElement) link.parentElement.hidden = true;
})();
