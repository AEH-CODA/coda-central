const TOKEN_KEY = 'token'

export function getToken() {
  return localStorage.getItem(TOKEN_KEY)
}

export function setToken(token) {
  localStorage.setItem(TOKEN_KEY, token)
}

export function clearToken() {
  localStorage.removeItem(TOKEN_KEY)
}

export function decodeRole(token) {
  try {
    const payload = token.split('.')[1]
    if (!payload) return 'user'
    return JSON.parse(atob(payload)).role || 'user'
  } catch {
    return 'user'
  }
}

export function decodeUserId(token) {
  try {
    const payload = token.split('.')[1]
    if (!payload) return null
    return JSON.parse(atob(payload)).sub || null
  } catch {
    return null
  }
}

export function decodeName(token) {
  try {
    const payload = token.split('.')[1]
    if (!payload) return null
    return JSON.parse(atob(payload)).name || null
  } catch {
    return null
  }
}

/**
 * Captures ?token= from the OAuth redirect and strips it from the URL.
 * Must run synchronously before the app renders — route guards decide
 * access from auth state on first render, before any effect would fire.
 */
export function captureOAuthToken() {
  const params = new URLSearchParams(window.location.search)
  const token = params.get('token')
  if (!token) return

  setToken(token)
  params.delete('token')
  const query = params.toString()
  window.history.replaceState({}, document.title, window.location.pathname + (query ? `?${query}` : ''))
}

const POST_LOGIN_REDIRECT_KEY = 'coda_post_login_redirect'

/**
 * Remembers where to send the user after login. Needed because the actual
 * sign-in round-trip leaves the app entirely (browser navigates to Google
 * and back through auth-service's own redirect, which always lands on `/`),
 * so in-memory router state (react-router's location.state) doesn't survive
 * it — only something durable like sessionStorage does. Used so a user who
 * isn't yet signed in to CODA can still land back on /oauth/authorize (e.g.
 * after clicking "Connect CODA account" from Biomni) instead of losing that
 * request at the root page.
 */
export function stashPostLoginRedirect(path) {
  sessionStorage.setItem(POST_LOGIN_REDIRECT_KEY, path)
}

export function consumePostLoginRedirect() {
  const path = sessionStorage.getItem(POST_LOGIN_REDIRECT_KEY)
  sessionStorage.removeItem(POST_LOGIN_REDIRECT_KEY)
  return path
}
