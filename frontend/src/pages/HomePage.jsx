import { Link } from 'react-router-dom';
import { Layout } from '../components/Layout.jsx';

export default function HomePage() {
  return (
    <Layout>
      <div className="card">
        <h2>OpsConsole P0</h2>
        <p className="muted" style={{ marginTop: 0 }}>
          섹션 카탈로그를 매니페스트(<code>ops/manifest.yml</code>)로부터 자동 구성합니다.
          현재 단계는 읽기 전용. 인증·헬스·콘텐츠 편집은 P1~P3에서 추가됩니다.
        </p>
        <div style={{ marginTop: 12 }}>
          <Link className="btn primary" to="/services">서비스 카탈로그 →</Link>
        </div>
      </div>

      <div className="card">
        <h2>로드맵</h2>
        <ul style={{ margin: 0, paddingLeft: 20, fontSize: 13, lineHeight: 1.8 }}>
          <li><strong>P0</strong> — 카탈로그 + 자동 스캔 + 웹 읽기전용 대시보드 (진행중)</li>
          <li><strong>P1</strong> — 담당자 지정 + 헬스 모니터링 + Slack 알림</li>
          <li><strong>P2</strong> — GitHub Bridge (Issue/PR 자동 생성)</li>
          <li><strong>P3</strong> — 콘텐츠 블록 에디터</li>
          <li><strong>P4</strong> — Tauri 트레이 Agent</li>
          <li><strong>P5</strong> — 권한·감사·SSO·배포</li>
        </ul>
      </div>
    </Layout>
  );
}
