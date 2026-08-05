// The live dashboard embed.
//
// Fill in the public dashboard URL from the `slo_public_url` output of
// `terraform apply` in terraform/live/observability — it looks like
// https://<stack>.grafana.net/public-dashboards/<access-token>
//
// Left empty, the page shows a "not yet wired" placeholder rather than an empty
// frame, so the site is never broken between the code landing and the apply.
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

  // Built here rather than hardcoded in the HTML so the URL lives in exactly one
  // place. The site CSP allows frame-src https://*.grafana.net.
  const iframe = document.createElement('iframe');
  iframe.src = PUBLIC_DASHBOARD_URL;
  iframe.title = 'cohns.net availability, latency, and cost — live';
  iframe.loading = 'lazy';
  iframe.referrerPolicy = 'no-referrer';
  frame.appendChild(iframe);

  if (link) link.href = PUBLIC_DASHBOARD_URL;
})();
