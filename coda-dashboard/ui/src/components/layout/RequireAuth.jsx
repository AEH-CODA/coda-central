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

// Doctors have full dataset access and no request-access workflow, so the
// requests pages aren't relevant to them — same treatment as RequireAdmin.
export function RequireNotDoctor() {
  const { isDoctor } = useAuth()

  if (isDoctor) {
    return <Navigate to="/" replace />
  }

  return <Outlet />
}
