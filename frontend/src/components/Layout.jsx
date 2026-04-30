import { Link, NavLink, useNavigate } from 'react-router-dom';
import { useAuth } from '../auth/AuthContext.jsx';

export function Layout({ children, crumbs }) {
  const { user, logout } = useAuth();
  const nav = useNavigate();

  return (
    <div className="app">
      <header className="app-header">
        <h1><Link to="/" style={{ color: 'inherit' }}>OpsConsole</Link></h1>
        <span className="subtitle">멀티 서비스 운영 콘솔</span>
        {user && (
          <nav>
            <NavLink to="/services" className={({ isActive }) => (isActive ? 'active' : '')}>
              Services
            </NavLink>
            <NavLink to="/my/sections" className={({ isActive }) => (isActive ? 'active' : '')}>
              My Sections
            </NavLink>
            <NavLink to="/my/change-requests" className={({ isActive }) => (isActive ? 'active' : '')}>
              Change Requests
            </NavLink>
          </nav>
        )}
        <div style={{ marginLeft: 'auto', fontSize: 13 }}>
          {user ? (
            <>
              <span className="muted">{user.email}</span>{' '}
              <span className="tag">{user.role}</span>{' '}
              <button
                className="btn"
                style={{ marginLeft: 8 }}
                onClick={() => { logout(); nav('/login'); }}
              >
                로그아웃
              </button>
            </>
          ) : (
            <Link className="btn" to="/login">로그인</Link>
          )}
        </div>
      </header>
      {crumbs && <Crumbs items={crumbs} />}
      {children}
    </div>
  );
}

function Crumbs({ items }) {
  return (
    <nav className="crumbs" aria-label="breadcrumb">
      {items.map((item, i) => (
        <span key={i}>
          {i > 0 && ' / '}
          {item.to ? <Link to={item.to}>{item.label}</Link> : <span>{item.label}</span>}
        </span>
      ))}
    </nav>
  );
}

export function ErrorBanner({ message }) {
  if (!message) return null;
  return <div className="error-banner">{message}</div>;
}

export function Loading({ label = '로딩 중...' }) {
  return (
    <div className="muted" style={{ padding: 16 }}>
      <span className="spinner" />{label}
    </div>
  );
}

export function Empty({ children }) {
  return <div className="empty">{children}</div>;
}

export function Tag({ kind, value }) {
  const cls = kind === 'level' ? `lvl-${value}` : kind === 'status' ? `s-${value}` : '';
  return <span className={`tag ${cls}`}>{value}</span>;
}
