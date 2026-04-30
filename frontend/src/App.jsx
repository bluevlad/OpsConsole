import { Navigate, Route, Routes } from 'react-router-dom';
import { AuthProvider } from './auth/AuthContext.jsx';
import { RequireAuth } from './auth/RequireAuth.jsx';
import ChangeRequestDetailPage from './pages/ChangeRequestDetailPage.jsx';
import ChangeRequestNewPage from './pages/ChangeRequestNewPage.jsx';
import DeviceApprovalPage from './pages/DeviceApprovalPage.jsx';
import HomePage from './pages/HomePage.jsx';
import LoginPage from './pages/LoginPage.jsx';
import MyChangeRequestsPage from './pages/MyChangeRequestsPage.jsx';
import MySectionsPage from './pages/MySectionsPage.jsx';
import PermissionsPage from './pages/PermissionsPage.jsx';
import SectionContentPage from './pages/SectionContentPage.jsx';
import SectionDetailPage from './pages/SectionDetailPage.jsx';
import SectionsListPage from './pages/SectionsListPage.jsx';
import ServicesListPage from './pages/ServicesListPage.jsx';

export default function App() {
  return (
    <AuthProvider>
      <Routes>
        <Route path="/" element={<HomePage />} />
        <Route path="/login" element={<LoginPage />} />
        <Route
          path="/device"
          element={<RequireAuth><DeviceApprovalPage /></RequireAuth>}
        />
        <Route
          path="/my/sections"
          element={<RequireAuth><MySectionsPage /></RequireAuth>}
        />
        <Route
          path="/my/change-requests"
          element={<RequireAuth><MyChangeRequestsPage /></RequireAuth>}
        />
        <Route
          path="/change-requests/new"
          element={<RequireAuth><ChangeRequestNewPage /></RequireAuth>}
        />
        <Route
          path="/change-requests/:id"
          element={<RequireAuth><ChangeRequestDetailPage /></RequireAuth>}
        />
        <Route
          path="/services"
          element={<RequireAuth><ServicesListPage /></RequireAuth>}
        />
        <Route
          path="/services/:code/sections"
          element={<RequireAuth><SectionsListPage /></RequireAuth>}
        />
        <Route
          path="/services/:code/sections/:section"
          element={<RequireAuth><SectionDetailPage /></RequireAuth>}
        />
        <Route
          path="/services/:code/sections/:section/content"
          element={<RequireAuth><SectionContentPage /></RequireAuth>}
        />
        <Route
          path="/services/:code/sections/:section/permissions"
          element={<RequireAuth role="ops_admin"><PermissionsPage /></RequireAuth>}
        />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </AuthProvider>
  );
}
