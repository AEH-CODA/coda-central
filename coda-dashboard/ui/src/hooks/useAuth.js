import { useCallback, useMemo, useSyncExternalStore } from 'react'
import { getToken, setToken, clearToken, decodeRole, decodeUserId } from '@/lib/auth'

function subscribe(callback) {
  window.addEventListener('storage', callback)
  return () => window.removeEventListener('storage', callback)
}

/**
 * Reads auth state from localStorage. login()/logout() dispatch a synthetic
 * StorageEvent so same-tab consumers re-render too — the native `storage`
 * event only fires in other tabs.
 */
export function useAuth() {
  const token = useSyncExternalStore(subscribe, getToken)
  const role = useMemo(() => (token ? decodeRole(token) : null), [token])
  const userId = useMemo(() => (token ? decodeUserId(token) : null), [token])

  const login = useCallback((newToken) => {
    setToken(newToken)
    window.dispatchEvent(new StorageEvent('storage'))
  }, [])

  const logout = useCallback(() => {
    clearToken()
    window.dispatchEvent(new StorageEvent('storage'))
  }, [])

  return {
    token,
    role,
    userId,
    isAuthenticated: Boolean(token),
    isAdmin: role === 'admin',
    isDataManager: role === 'data-manager',
    // Admins and data managers both review/approve access requests; only
    // admins additionally get the Role Management page.
    canManageRequests: role === 'admin' || role === 'data-manager',
    isDoctor: role === 'doctor',
    login,
    logout,
  }
}
