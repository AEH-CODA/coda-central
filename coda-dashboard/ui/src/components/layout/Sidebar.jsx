import { NavLink, useNavigate } from 'react-router-dom'
import { Search, History, LayoutGrid, ShieldCheck, UserCog, LogOut, User } from 'lucide-react'
import { useAuth } from '@/hooks/useAuth'

const baseNavItems = [
  { to: '/', label: 'Query Data', icon: Search, end: true },
  { to: '/requests', label: 'My Data Requests', icon: History },
  { to: '/model-workspace', label: 'Model Workspace', icon: LayoutGrid },
]

function navLinkClass({ isActive }) {
  return [
    'flex items-center gap-3 rounded-sm border-l-2 px-3 py-2.5 text-sm font-medium transition-colors',
    isActive
      ? 'border-primary bg-muted text-primary'
      : 'border-transparent text-muted-foreground hover:bg-muted hover:text-foreground',
  ].join(' ')
}

export function Sidebar() {
  const { isAdmin, canManageRequests, hasFullDatasetAccess, userName, logout } = useAuth()
  const navigate = useNavigate()

  // Doctors/admins/data-managers have full dataset access with no
  // access-request workflow of their own, so the requests page/link isn't
  // relevant to them.
  const navItems = hasFullDatasetAccess ? baseNavItems.filter((item) => item.to !== '/requests') : baseNavItems

  function handleSignOut() {
    logout()
    navigate('/login', { replace: true })
  }

  return (
    <aside className="flex h-screen w-60 shrink-0 flex-col border-r border-border bg-surface">
      <div className="flex shrink-0 items-center gap-3 px-4 py-5">
        <div className="flex h-9 w-9 items-center justify-center rounded-md bg-primary text-sm font-bold text-primary-foreground">
          C
        </div>
        <div>
          <p className="text-lg font-semibold leading-tight text-foreground">CODA</p>
          <p className="text-xs text-muted-foreground">Data Discovery</p>
        </div>
      </div>

      <nav className="flex min-h-0 flex-1 flex-col gap-1 overflow-y-auto px-3">
        {navItems.map(({ to, label, icon: Icon, end }) => (
          <NavLink key={to} to={to} end={end} className={navLinkClass}>
            <Icon size={18} strokeWidth={1.8} />
            {label}
          </NavLink>
        ))}

        {canManageRequests && (
          <NavLink to="/admin/requests" className={navLinkClass}>
            <ShieldCheck size={18} strokeWidth={1.8} />
            Data Access Requests
          </NavLink>
        )}

        {isAdmin && (
          <NavLink to="/admin/roles" className={navLinkClass}>
            <UserCog size={18} strokeWidth={1.8} />
            Role Management
          </NavLink>
        )}
      </nav>

      <div className="shrink-0 border-t border-border px-3 py-4">
        {userName && (
          <div className="flex items-center gap-3 px-3 py-2 text-sm font-medium text-foreground">
            <User size={18} strokeWidth={1.8} className="text-muted-foreground" />
            <span className="truncate">{userName}</span>
          </div>
        )}
        <button
          type="button"
          onClick={handleSignOut}
          className="flex w-full cursor-pointer items-center gap-3 rounded-sm px-3 py-2.5 text-sm font-medium text-muted-foreground transition-colors hover:bg-muted hover:text-destructive"
        >
          <LogOut size={18} strokeWidth={1.8} />
          Sign Out
        </button>
      </div>
    </aside>
  )
}
