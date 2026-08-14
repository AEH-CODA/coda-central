import { Navigate, Outlet, useLocation } from 'react-router-dom'
import { useAuth } from '@/hooks/useAuth'

export function RequireAuth() {
  const { isAuthenticated } = useAuth()
  const location = useLocation()

  if (!isAuthenticated) {
    return <Navigate to="/login" replace state={{ from: location }} />
  }

  return <Outlet />
}

// Admin only — Role Management is more sensitive than reviewing requests, so
// it's kept separate from RequireRequestManager below.
export function RequireAdmin() {
  const { isAdmin } = useAuth()

  if (!isAdmin) {
    return <Navigate to="/" replace />
  }

  return <Outlet />
}

// Admins and data managers both review/approve access requests.
export function RequireRequestManager() {
  const { canManageRequests } = useAuth()

  if (!canManageRequests) {
    return <Navigate to="/" replace />
  }

  return <Outlet />
}

// Doctors, admins, and data managers have full dataset access and no
// access-request workflow of their own, so the "My Data Requests" page isn't
// relevant to them.
export function RequireNotFullDatasetAccess() {
  const { hasFullDatasetAccess } = useAuth()

  if (hasFullDatasetAccess) {
    return <Navigate to="/" replace />
  }

  return <Outlet />
}
