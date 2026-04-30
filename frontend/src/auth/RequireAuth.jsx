import { Navigate, useLocation } from 'react-router-dom';
import { Layout, Loading } from '../components/Layout.jsx';
import { useAuth } from './AuthContext.jsx';

export function RequireAuth({ children, role }) {
  const { user, loading } = useAuth();
  const location = useLocation();

  if (loading) return <Loading label="세션 확인 중..." />;
  if (!user) {
    return <Navigate to="/login" state={{ from: location.pathname }} replace />;
  }
  if (role && user.role !== role) {
    return (
      <Layout>
        <div className="error-banner">
          이 페이지는 <code>{role}</code> 권한이 필요합니다 (현재: <code>{user.role}</code>).
        </div>
      </Layout>
    );
  }
  return children;
}
