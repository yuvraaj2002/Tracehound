import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { BrowserRouter, Navigate, Route, Routes } from 'react-router'
import './index.css'
import App from './App.tsx'
import AuthProvider from './auth/AuthProvider.tsx'
import { RedirectIfSignedIn, RequireAuth } from './auth/guards.tsx'
import SignIn from './pages/SignIn.tsx'
import AuthCallback from './pages/AuthCallback.tsx'
import Home from './pages/Home.tsx'
import Workspace from './pages/Workspace.tsx'
import ApiKeys from './pages/ApiKeys.tsx'

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <BrowserRouter>
      <AuthProvider>
        <Routes>
          <Route index element={<App />} />
          <Route path="signin" element={<RedirectIfSignedIn><SignIn /></RedirectIfSignedIn>} />
          <Route path="auth/callback" element={<AuthCallback />} />
          <Route path="app" element={<RequireAuth><Home /></RequireAuth>} />
          <Route path="app/incidents" element={<RequireAuth><Workspace /></RequireAuth>} />
          <Route path="app/api-keys" element={<RequireAuth><ApiKeys /></RequireAuth>} />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </AuthProvider>
    </BrowserRouter>
  </StrictMode>,
)
