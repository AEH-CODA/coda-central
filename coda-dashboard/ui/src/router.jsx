import { createBrowserRouter } from 'react-router-dom'
import { AppShell } from '@/components/layout/AppShell'
import {
  RequireAuth,
  RequireAdmin,
  RequireRequestManager,
  RequireNotFullDatasetAccess,
} from '@/components/layout/RequireAuth'
import { LoginPage } from '@/pages/LoginPage'
import { OAuthAuthorizePage } from '@/pages/OAuthAuthorizePage'
import { QueryDataPage } from '@/pages/QueryDataPage'
import { SavedDatasetsPage } from '@/pages/SavedDatasetsPage'
import { MyDataRequestsPage } from '@/pages/MyDataRequestsPage'
import { DataAccessRequestsPage } from '@/pages/DataAccessRequestsPage'
import { RoleManagementPage } from '@/pages/RoleManagementPage'
import { ModelWorkspacePage } from '@/pages/ModelWorkspacePage'
import { OctAnalysisPage } from '@/pages/OctAnalysisPage'
import { OctReportPage } from '@/pages/OctReportPage'

export const router = createBrowserRouter([
  { path: '/login', element: <LoginPage /> },
  {
    element: <RequireAuth />,
    children: [
      // Standalone (no sidebar chrome), like /login — this is a one-off
      // consent screen reached via an external redirect (e.g. from Biomni),
      // not a page someone navigates the app to.
      { path: '/oauth/authorize', element: <OAuthAuthorizePage /> },
      {
        element: <AppShell />,
        children: [
          { path: '/', element: <QueryDataPage /> },
          { path: '/saved-datasets', element: <SavedDatasetsPage /> },
          {
            element: <RequireNotFullDatasetAccess />,
            children: [{ path: '/requests', element: <MyDataRequestsPage /> }],
          },
          { path: '/model-workspace', element: <ModelWorkspacePage /> },
          { path: '/oct-analysis', element: <OctAnalysisPage /> },
          { path: '/oct-analysis/:jobId', element: <OctReportPage /> },
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
