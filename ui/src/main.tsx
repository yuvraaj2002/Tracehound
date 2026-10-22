import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { BrowserRouter, Navigate, Route, Routes } from 'react-router'
import './index.css'
import App from './App.tsx'
import AuthProvider from './auth/AuthProvider.tsx'
import { RedirectIfSignedIn, RequireAuth } from './auth/guards.tsx'
import SignIn from './pages/SignIn.tsx'
import AuthCallback from './pages/AuthCallback.tsx'
import Workspace from './pages/Workspace.tsx'

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <BrowserRouter>
      <AuthProvider>
        <Routes>
          <Route index element={<App />} />
          <Route path="signin" element={<RedirectIfSignedIn><SignIn /></RedirectIfSignedIn>} />
          <Route path="auth/callback" element={<AuthCallback />} />
          <Route path="app" element={<RequireAuth><Workspace /></RequireAuth>} />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </AuthProvider>
    </BrowserRouter>
  </StrictMode>,
)
