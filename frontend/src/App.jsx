import { Navigate, Route, Routes } from 'react-router-dom';
import HomePage from './pages/HomePage.jsx';
import LoginPage from './pages/LoginPage.jsx';
import SectionDetailPage from './pages/SectionDetailPage.jsx';
import SectionsListPage from './pages/SectionsListPage.jsx';
import ServicesListPage from './pages/ServicesListPage.jsx';

export default function App() {
  return (
    <Routes>
      <Route path="/" element={<HomePage />} />
      <Route path="/login" element={<LoginPage />} />
      <Route path="/services" element={<ServicesListPage />} />
      <Route path="/services/:code/sections" element={<SectionsListPage />} />
      <Route path="/services/:code/sections/:section" element={<SectionDetailPage />} />
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}
