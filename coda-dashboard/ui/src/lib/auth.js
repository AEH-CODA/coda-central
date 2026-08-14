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
