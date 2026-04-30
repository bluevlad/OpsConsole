import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { listMySections, triggerHealthProbe } from '../api/catalog.js';
import { useAuth } from '../auth/AuthContext.jsx';
import { HealthDot } from '../components/Health.jsx';
import { Empty, ErrorBanner, Layout, Loading, Tag } from '../components/Layout.jsx';

export default function MySectionsPage() {
  const { user } = useAuth();
  const [rows, setRows] = useState(null);
  const [error, setError] = useState(null);
  const [probing, setProbing] = useState(false);

  async function refresh() {
    try {
      setError(null);
      const data = await listMySections();
      setRows(data);
    } catch (err) {
      const msg = err.response?.data?.detail || err.message || 'My sections 조회 실패';
      setError(msg);
      setRows([]);
    }
  }

  useEffect(() => { refresh(); }, []);

  async function onProbe() {
    setProbing(true);
    try {
      await triggerHealthProbe();
      await refresh();
    } catch (err) {
      const msg = err.response?.data?.detail || err.message || '헬스 점검 실패';
      setError(msg);
    } finally {
      setProbing(false);
    }
  }

  return (
    <Layout crumbs={[{ to: '/', label: 'Home' }, { label: 'My Sections' }]}>
      <ErrorBanner message={error} />

      <div className="action-bar">
        <span className="muted" style={{ fontSize: 13 }}>
          내가 owner / backup / 권한 보유한 섹션 + 최근 헬스
        </span>
        {user?.role === 'ops_admin' && (
          <button className="btn" onClick={onProbe} disabled={probing} style={{ marginLeft: 'auto' }}>
            {probing ? <span className="spinner" /> : null}지금 헬스 점검
          </button>
        )}
      </div>

      {rows === null && !error && <Loading label="내 섹션 조회 중..." />}

      {rows && rows.length === 0 && !error && (
        <Empty>
          담당하는 섹션이 없습니다.
          <br />
          매니페스트의 <code>owner</code>/<code>backup</code> 이메일 또는 ops_admin 의 권한 부여로 등록됩니다.
        </Empty>
      )}

      {rows && rows.length > 0 && (
        <div className="card" style={{ padding: 0 }}>
          <table>
            <thead>
              <tr>
                <th style={{ width: 36 }}></th>
                <th style={{ width: 180 }}>서비스</th>
                <th style={{ width: 180 }}>섹션</th>
                <th style={{ width: 90 }}>레벨</th>
                <th style={{ width: 90 }}>상태</th>
                <th style={{ width: 90 }}>관계</th>
                <th>최근 헬스</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((r) => (
                <tr key={r.section_id}>
                  <td><HealthDot summary={r.health} /></td>
                  <td>
                    <Link to={`/services/${r.service_code}/sections`}>
                      {r.service_display_name}
                    </Link>
                  </td>
                  <td>
                    <Link to={`/services/${r.service_code}/sections/${r.section_code}`}>
                      <code>{r.section_code}</code>
                    </Link>
                    <div className="muted" style={{ fontSize: 11.5 }}>{r.section_name}</div>
                  </td>
                  <td><Tag kind="level" value={r.level} /></td>
                  <td><Tag kind="status" value={r.status} /></td>
                  <td className="muted">{r.relation}</td>
                  <td><HealthDot summary={r.health} withLabel /></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </Layout>
  );
}
