import { useEffect, useState } from 'react';
import { cmd } from './api/tauri.js';
import DeviceLoginPanel from './pages/DeviceLoginPanel.jsx';
import MySectionsPanel from './pages/MySectionsPanel.jsx';
import ChangeRequestForm from './pages/ChangeRequestForm.jsx';

const TABS = [
  { id: 'sections', label: '내 섹션' },
  { id: 'cr', label: '변경요청' },
];

export default function App() {
  const [token, setToken] = useState(null);
  const [tab, setTab] = useState('sections');
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    cmd.loadToken()
      .then((t) => { setToken(t || null); setLoading(false); })
      .catch(() => setLoading(false));
  }, []);

  if (loading) return <div className="tray-app muted">세션 확인 중...</div>;

  if (!token) {
    return (
      <div className="tray-app">
        <DeviceLoginPanel onLogin={(t) => setToken(t)} />
      </div>
    );
  }

  return (
    <div className="tray-app">
      <div className="row" style={{ marginBottom: 6 }}>
        <strong>OpsConsole</strong>
        <button
          className="btn"
          style={{ marginLeft: 'auto', fontSize: 11 }}
          onClick={async () => { await cmd.clearToken(); setToken(null); }}
        >
          로그아웃
        </button>
      </div>
      <div className="tabs">
        {TABS.map((t) => (
          <button
            key={t.id}
            className={tab === t.id ? 'active' : ''}
            onClick={() => setTab(t.id)}
          >
            {t.label}
          </button>
        ))}
      </div>
      {tab === 'sections' && <MySectionsPanel />}
      {tab === 'cr' && <ChangeRequestForm />}
    </div>
  );
}
