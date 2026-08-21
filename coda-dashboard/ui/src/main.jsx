import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { RouterProvider } from 'react-router-dom'
import './index.css'
import './lib/chartSetup'
import { router } from './router'
import { captureOAuthToken } from '@/lib/auth'

// Must run before the first render — route guards read auth state
// synchronously, before any effect would get a chance to fire.
captureOAuthToken()

createRoot(document.getElementById('root')).render(
  <StrictMode>
    <RouterProvider router={router} />
  </StrictMode>,
)
