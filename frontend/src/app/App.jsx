import { BrowserRouter, Navigate, Route, Routes } from 'react-router-dom'
import { AuthProvider } from '@/auth/AuthContext'
import { AppLayout } from '@/components/AppLayout'
import { ProtectedRoute } from '@/components/ProtectedRoute'
import { RequireRole } from '@/components/RequireRole'
import { AdminPage } from '@/pages/AdminPage'
import { AuditPage } from '@/pages/AuditPage'
import { DashboardPage } from '@/pages/DashboardPage'
import { DocumentDetailsPage } from '@/pages/DocumentDetailsPage'
import { DocumentPermissionsPage } from '@/pages/DocumentPermissionsPage'
import { DocumentsPage } from '@/pages/DocumentsPage'
import { LoginPage } from '@/pages/LoginPage'
import { NotFoundPage } from '@/pages/NotFoundPage'
import { RegisterPage } from '@/pages/RegisterPage'
import { SharedDocumentsPage } from '@/pages/SharedDocumentsPage'
import { UploadPage } from '@/pages/UploadPage'

export function App() {
  return (
    <BrowserRouter>
      <AuthProvider>
        <Routes>
          <Route path="/login" element={<LoginPage />} />
          <Route path="/register" element={<RegisterPage />} />
          <Route element={<ProtectedRoute />}>
            <Route element={<AppLayout />}>
              <Route index element={<Navigate to="/dashboard" replace />} />
              <Route path="/dashboard" element={<DashboardPage />} />
              <Route path="/documents" element={<DocumentsPage />} />
              <Route path="/upload" element={<UploadPage />} />
              <Route path="/shared-with-me" element={<SharedDocumentsPage />} />
              <Route
                path="/documents/:documentId/permissions"
                element={<DocumentPermissionsPage />}
              />
              <Route path="/documents/:documentId" element={<DocumentDetailsPage />} />
              <Route element={<RequireRole role="ADMINISTRATOR" />}>
                <Route path="/admin" element={<AdminPage />} />
                <Route path="/admin/audit" element={<AuditPage />} />
              </Route>
              <Route path="*" element={<NotFoundPage />} />
            </Route>
          </Route>
        </Routes>
      </AuthProvider>
    </BrowserRouter>
  )
}
