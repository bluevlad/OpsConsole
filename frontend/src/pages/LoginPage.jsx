import { useState } from 'react';
import { Navigate, useLocation } from 'react-router-dom';
import { GoogleSignInButton } from '../auth/GoogleSignInButton.jsx';
import { useAuth } from '../auth/AuthContext.jsx';
import { ErrorBanner, Layout } from '../components/Layout.jsx';

export default function LoginPage() {
  const { user } = useAuth();
  const location = useLocation();
  const [error, setError] = useState(null);

  if (user) {
    const from = location.state?.from || '/services';
    return <Navigate to={from} replace />;
  }

  return (
    <Layout crumbs={[{ to: '/', label: 'Home' }, { label: 'Login' }]}>
      <div className="card" style={{ maxWidth: 480 }}>
        <h2>로그인</h2>
        <p className="muted" style={{ marginTop: 0 }}>
          Google 계정으로 로그인하면 OpsConsole 자체 JWT가 발급됩니다.
          첫 가입자는 자동으로 <code>ops_admin</code>, 그 이후엔 <code>ops_member</code> 입니다.
        </p>
        <ErrorBanner message={error} />
        <div style={{ marginTop: 16 }}>
          <GoogleSignInButton
            onSuccess={() => setError(null)}
            onError={(msg) => setError(msg)}
          />
        </div>
        <dl className="kv" style={{ marginTop: 24 }}>
          <dt>Provider</dt><dd>Google Identity Services (ID Token)</dd>
          <dt>JWT 알고리즘</dt><dd>HS256 / 12h expire</dd>
          <dt>역할</dt><dd>ops_admin / ops_member / ops_viewer</dd>
        </dl>
      </div>
    </Layout>
  );
}
