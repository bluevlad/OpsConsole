import { Routes, Route, Link, Navigate } from 'react-router-dom';

// P0 §0 단계: 페이지는 빈 stub. 실제 구현은 §3에서.
function HomePage() {
  return (
    <main style={{ padding: 24, fontFamily: 'system-ui, -apple-system, sans-serif' }}>
      <h1>OpsConsole</h1>
      <p>P0 부트스트랩 단계 — 페이지 stub.</p>
      <ul>
        <li><Link to="/login">/login</Link> — Google OAuth 로그인 (P0 §2)</li>
        <li><Link to="/services">/services</Link> — 서비스 목록 (P0 §3)</li>
      </ul>
    </main>
  );
}

function LoginPage() {
  return <main style={{ padding: 24 }}><h2>Login (TODO P0 §2)</h2></main>;
}

function ServicesListPage() {
  return <main style={{ padding: 24 }}><h2>Services (TODO P0 §3)</h2></main>;
}

function SectionsListPage() {
  return <main style={{ padding: 24 }}><h2>Sections (TODO P0 §3)</h2></main>;
}

function SectionDetailPage() {
  return <main style={{ padding: 24 }}><h2>Section detail (TODO P0 §3)</h2></main>;
}

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
