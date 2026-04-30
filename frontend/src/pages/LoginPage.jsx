import { Layout } from '../components/Layout.jsx';

export default function LoginPage() {
  return (
    <Layout crumbs={[{ to: '/', label: 'Home' }, { label: 'Login' }]}>
      <div className="card">
        <h2>Login</h2>
        <p className="muted">
          Google OAuth 로그인은 P0 §2 auth 단계에서 활성화됩니다.
          <br />
          현재 단계는 인증 없이 읽기 전용 카탈로그만 노출됩니다.
        </p>
        <div className="kv">
          <dt>예정 Provider</dt><dd>Google OAuth 2.0</dd>
          <dt>JWT</dt><dd>HS256 / 12h expire</dd>
          <dt>역할</dt><dd>ops_admin / ops_member / ops_viewer</dd>
        </div>
      </div>
    </Layout>
  );
}
