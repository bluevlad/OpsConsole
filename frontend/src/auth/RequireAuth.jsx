import { Navigate, useLocation } from 'react-router-dom';
import { Loading } from '../components/Layout.jsx';
import { useAuth } from './AuthContext.jsx';

export function RequireAuth({ children }) {
  const { user, loading } = useAuth();
  const location = useLocation();

  if (loading) return <Loading label="세션 확인 중..." />;
  if (!user) {
    return <Navigate to="/login" state={{ from: location.pathname }} replace />;
  }
  return children;
}
