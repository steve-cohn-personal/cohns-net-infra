// Sign-in for cohns.net, against the Cognito hosted UI.
//
// OAuth 2.0 authorization-code flow with PKCE — the right pattern for a public
// SPA: no client secret in the browser, and tokens arrive via a back-channel
// exchange rather than in the URL. The pool is shared across environments, so its
// public identifiers (client id + hosted-UI domain) are the same everywhere and
// are safe to ship in client code; they are not secrets.
//
// Flow:
//   signIn()  -> redirect to the hosted UI /oauth2/authorize
//   <return>  -> Cognito redirects back to the origin root with ?code=...
//   onload    -> exchange the code at /oauth2/token, store tokens, restore the page
//   signOut() -> clear tokens, redirect through the hosted UI /logout
//
// The registered callback/logout URLs are the origin roots (see the Cognito web
// client), so redirect_uri is always `${origin}/` and the landing page (the site
// homepage) runs the exchange. A `state` value carries the path to return to.

(function () {
  "use strict";

  var COGNITO_DOMAIN = "https://cohns-net-auth.auth.us-west-2.amazoncognito.com";
  var CLIENT_ID = "6qsjj1rmeaakhjbbcuqc5br9nj";
  var SCOPES = "openid email profile";

  var REDIRECT_URI = location.origin + "/"; // must match a registered callback URL
  var STORE_KEY = "cohns.auth.tokens";      // localStorage: the token set
  var VERIFIER_KEY = "cohns.auth.pkce";     // sessionStorage: PKCE verifier + return path

  // --- PKCE helpers ---------------------------------------------------------

  function randomString(bytes) {
    var a = new Uint8Array(bytes);
    crypto.getRandomValues(a);
    return base64url(a.buffer);
  }

  function base64url(buf) {
    var bytes = new Uint8Array(buf);
    var s = "";
    for (var i = 0; i < bytes.length; i++) s += String.fromCharCode(bytes[i]);
    return btoa(s).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
  }

  async function challengeFor(verifier) {
    var digest = await crypto.subtle.digest("SHA-256", new TextEncoder().encode(verifier));
    return base64url(digest);
  }

  // --- token store ----------------------------------------------------------

  function saveTokens(t) {
    // expires_in is seconds from now; record an absolute expiry with a little slack.
    t.expires_at = Date.now() + (t.expires_in - 30) * 1000;
    localStorage.setItem(STORE_KEY, JSON.stringify(t));
  }

  function loadTokens() {
    try { return JSON.parse(localStorage.getItem(STORE_KEY)); } catch (e) { return null; }
  }

  function clearTokens() {
    localStorage.removeItem(STORE_KEY);
  }

  function decodeJwt(jwt) {
    try {
      var p = jwt.split(".")[1].replace(/-/g, "+").replace(/_/g, "/");
      return JSON.parse(decodeURIComponent(escape(atob(p))));
    } catch (e) { return null; }
  }

  // --- public surface -------------------------------------------------------

  async function signIn(returnPath) {
    var verifier = randomString(48);
    var state = randomString(16);
    sessionStorage.setItem(VERIFIER_KEY, JSON.stringify({
      verifier: verifier,
      state: state,
      returnPath: returnPath || (location.pathname + location.search),
    }));
    var url = COGNITO_DOMAIN + "/oauth2/authorize?" + new URLSearchParams({
      response_type: "code",
      client_id: CLIENT_ID,
      redirect_uri: REDIRECT_URI,
      scope: SCOPES,
      state: state,
      code_challenge_method: "S256",
      code_challenge: await challengeFor(verifier),
    }).toString();
    location.assign(url);
  }

  function signOut() {
    clearTokens();
    var url = COGNITO_DOMAIN + "/logout?" + new URLSearchParams({
      client_id: CLIENT_ID,
      logout_uri: REDIRECT_URI,
    }).toString();
    location.assign(url);
  }

  async function exchangeCode(code, verifier) {
    var r = await fetch(COGNITO_DOMAIN + "/oauth2/token", {
      method: "POST",
      headers: { "Content-Type": "application/x-www-form-urlencoded" },
      body: new URLSearchParams({
        grant_type: "authorization_code",
        client_id: CLIENT_ID,
        code: code,
        redirect_uri: REDIRECT_URI,
        code_verifier: verifier,
      }).toString(),
    });
    if (!r.ok) throw new Error("token exchange failed: " + r.status);
    return r.json();
  }

  async function refresh(refreshToken) {
    var r = await fetch(COGNITO_DOMAIN + "/oauth2/token", {
      method: "POST",
      headers: { "Content-Type": "application/x-www-form-urlencoded" },
      body: new URLSearchParams({
        grant_type: "refresh_token",
        client_id: CLIENT_ID,
        refresh_token: refreshToken,
      }).toString(),
    });
    if (!r.ok) throw new Error("refresh failed: " + r.status);
    var t = await r.json();
    t.refresh_token = t.refresh_token || refreshToken; // refresh grant may omit it
    return t;
  }

  function isSignedIn() {
    var t = loadTokens();
    return !!(t && t.id_token && Date.now() < t.expires_at);
  }

  function getUser() {
    var t = loadTokens();
    if (!t || !t.id_token) return null;
    var claims = decodeJwt(t.id_token) || {};
    return {
      email: claims.email,
      groups: claims["cognito:groups"] || [],
      isModerator: (claims["cognito:groups"] || []).indexOf("moderators") !== -1,
    };
  }

  // The ID token is what the content API verifies (audience = the app client id).
  // Refresh transparently if it has expired but we still hold a refresh token.
  async function getIdToken() {
    var t = loadTokens();
    if (!t) return null;
    if (Date.now() < t.expires_at) return t.id_token;
    if (!t.refresh_token) { clearTokens(); return null; }
    try {
      var fresh = await refresh(t.refresh_token);
      saveTokens(fresh);
      return fresh.id_token;
    } catch (e) {
      clearTokens();
      return null;
    }
  }

  // Convenience for authenticated API calls once the API is live.
  async function authFetch(url, opts) {
    opts = opts || {};
    var token = await getIdToken();
    opts.headers = Object.assign({}, opts.headers, token ? { Authorization: "Bearer " + token } : {});
    return fetch(url, opts);
  }

  // Run the code exchange if we landed on the OAuth redirect. Returns the path to
  // restore (or null). Kept side-effect-light so pages can await it before painting.
  async function handleRedirect() {
    var params = new URLSearchParams(location.search);
    var code = params.get("code");
    if (!code) return null;

    var pending = null;
    try { pending = JSON.parse(sessionStorage.getItem(VERIFIER_KEY)); } catch (e) { /* ignore */ }
    sessionStorage.removeItem(VERIFIER_KEY);

    // Drop the code/state from the URL regardless of outcome.
    var returnPath = (pending && pending.returnPath) || location.pathname;
    history.replaceState({}, document.title, returnPath);

    if (!pending || pending.state !== params.get("state")) return returnPath; // CSRF guard
    try {
      var tokens = await exchangeCode(code, pending.verifier);
      saveTokens(tokens);
    } catch (e) {
      console.error(e);
    }
    return returnPath;
  }

  // --- self-rendering sign-in bar ------------------------------------------

  function renderBar() {
    var bar = document.getElementById("authbar");
    if (!bar) return;
    bar.innerHTML = "";
    if (isSignedIn()) {
      var user = getUser();
      var who = document.createElement("span");
      who.className = "authbar-who";
      who.textContent = user.email + (user.isModerator ? " · moderator" : "");
      var out = document.createElement("button");
      out.className = "authbar-btn";
      out.textContent = "Sign out";
      out.addEventListener("click", signOut);
      bar.appendChild(who);
      bar.appendChild(out);
    } else {
      var inBtn = document.createElement("button");
      inBtn.className = "authbar-btn";
      inBtn.textContent = "Sign in";
      inBtn.addEventListener("click", function () { signIn(); });
      bar.appendChild(inBtn);
    }
  }

  window.cohnsAuth = {
    signIn: signIn,
    signOut: signOut,
    isSignedIn: isSignedIn,
    getUser: getUser,
    getIdToken: getIdToken,
    authFetch: authFetch,
  };

  document.addEventListener("DOMContentLoaded", function () {
    handleRedirect().then(renderBar);
  });
})();
