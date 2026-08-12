import { createBrowserRouter } from 'react-router-dom'
import { AppShell } from '@/components/layout/AppShell'
import { RequireAuth, RequireAdmin, RequireRequestManager, RequireNotDoctor } from '@/components/layout/RequireAuth'
import { LoginPage } from '@/pages/LoginPage'
import { QueryDataPage } from '@/pages/QueryDataPage'
import { MyDataRequestsPage } from '@/pages/MyDataRequestsPage'
import { DataAccessRequestsPage } from '@/pages/DataAccessRequestsPage'
import { RoleManagementPage } from '@/pages/RoleManagementPage'
import { ModelWorkspacePage } from '@/pages/ModelWorkspacePage'

export const router = createBrowserRouter([
  { path: '/login', element: <LoginPage /> },
  {
    element: <RequireAuth />,
    children: [
      {
        element: <AppShell />,
        children: [
          { path: '/', element: <QueryDataPage /> },
          {
            element: <RequireNotDoctor />,
            children: [{ path: '/requests', element: <MyDataRequestsPage /> }],
          },
          { path: '/model-workspace', element: <ModelWorkspacePage /> },
          {
            element: <RequireRequestManager />,
            children: [{ path: '/admin/requests', element: <DataAccessRequestsPage /> }],
          },
          {
            element: <RequireAdmin />,
            children: [{ path: '/admin/roles', element: <RoleManagementPage /> }],
          },
        ],
      },
    ],
  },
])
