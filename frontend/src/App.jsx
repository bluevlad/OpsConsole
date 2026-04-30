import { Navigate, Route, Routes } from 'react-router-dom';
import { AuthProvider } from './auth/AuthContext.jsx';
import { RequireAuth } from './auth/RequireAuth.jsx';
import HomePage from './pages/HomePage.jsx';
import LoginPage from './pages/LoginPage.jsx';
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
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </AuthProvider>
  );
}
