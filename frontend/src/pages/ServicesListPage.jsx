import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { Empty, ErrorBanner, Layout, Loading, Tag } from '../components/Layout.jsx';
import { listServices } from '../api/catalog.js';

export default function ServicesListPage() {
  const [services, setServices] = useState(null);
  const [error, setError] = useState(null);

  useEffect(() => {
    let cancelled = false;
    listServices()
      .then((data) => { if (!cancelled) setServices(data); })
      .catch((err) => {
        if (cancelled) return;
        const msg = err.response?.data?.detail || err.message || '서비스 목록 조회 실패';
        setError(msg);
        setServices([]);
      });
    return () => { cancelled = true; };
  }, []);

  return (
    <Layout crumbs={[{ to: '/', label: 'Home' }, { label: 'Services' }]}>
      <ErrorBanner message={error} />

      {services === null && <Loading label="서비스 카탈로그 조회 중..." />}

      {services && services.length === 0 && !error && (
        <Empty>
          등록된 서비스가 없습니다.
          <br />
          <code>python -m scripts.seed_allergyinsight</code> 또는 <code>POST /api/catalog/sync</code> 로 매니페스트를 동기화하세요.
        </Empty>
      )}

      {services && services.length > 0 && (
        <div className="card" style={{ padding: 0 }}>
          <table>
            <thead>
              <tr>
                <th style={{ width: 200 }}>서비스 코드</th>
                <th>표시명</th>
                <th style={{ width: 100 }}>섹션 수</th>
                <th style={{ width: 120 }}>상태</th>
                <th>최근 동기화</th>
              </tr>
            </thead>
            <tbody>
              {services.map((s) => (
                <tr key={s.id}>
                  <td>
                    <Link to={`/services/${s.code}/sections`}>
                      <code>{s.code}</code>
                    </Link>
                  </td>
                  <td>{s.display_name}</td>
                  <td>{s.section_count}</td>
                  <td><Tag kind="status" value={s.status} /></td>
                  <td className="muted">
                    {s.last_synced_at
                      ? new Date(s.last_synced_at).toLocaleString('ko-KR')
                      : '—'}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </Layout>
  );
}
