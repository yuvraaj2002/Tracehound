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
import IncidentDetail from './pages/IncidentDetail.tsx'
import AgentModels from './pages/AgentModels'
import Billing from './pages/Billing'
import ApiKeys from './pages/ApiKeys.tsx'
import Integrations from './pages/Integrations.tsx'
import Catalog from './pages/Catalog.tsx'
import ApiDocs from './pages/ApiDocs.tsx'
import { SmoothScroll } from './useSmoothScroll'
import ThemeProvider from './ThemeProvider.tsx'

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <BrowserRouter>
      <SmoothScroll />
      <ThemeProvider>
      <AuthProvider>
        <Routes>
          <Route index element={<App />} />
          <Route path="signin" element={<RedirectIfSignedIn><SignIn /></RedirectIfSignedIn>} />
          <Route path="auth/callback" element={<AuthCallback />} />
          <Route path="app" element={<RequireAuth><Home /></RequireAuth>} />
          <Route path="app/incidents" element={<RequireAuth><Workspace /></RequireAuth>} />
          <Route path="app/incidents/:incidentId" element={<RequireAuth><IncidentDetail /></RequireAuth>} />
          <Route path="app/api-keys" element={<RequireAuth><ApiKeys /></RequireAuth>} />
          <Route path="app/integrations" element={<RequireAuth><Integrations /></RequireAuth>} />
          <Route path="app/catalog" element={<RequireAuth><Catalog /></RequireAuth>} />
          <Route path="app/models" element={<RequireAuth><AgentModels /></RequireAuth>} />
          <Route path="app/billing" element={<RequireAuth><Billing /></RequireAuth>} />
          <Route path="app/docs" element={<RequireAuth><ApiDocs /></RequireAuth>} />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </AuthProvider>
      </ThemeProvider>
    </BrowserRouter>
  </StrictMode>,
)
