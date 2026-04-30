import { useEffect, useState } from 'react';
import { Link, useParams } from 'react-router-dom';
import { Empty, ErrorBanner, Layout, Loading, Tag } from '../components/Layout.jsx';
import { HealthDot } from '../components/Health.jsx';
import { getService, listSections } from '../api/catalog.js';

export default function SectionsListPage() {
  const { code } = useParams();
  const [service, setService] = useState(null);
  const [sections, setSections] = useState(null);
  const [error, setError] = useState(null);

  useEffect(() => {
    let cancelled = false;
    Promise.all([getService(code), listSections(code)])
      .then(([svc, secs]) => {
        if (cancelled) return;
        setService(svc);
        setSections(secs);
      })
      .catch((err) => {
        if (cancelled) return;
        const msg = err.response?.data?.detail || err.message || '섹션 조회 실패';
        setError(msg);
        setSections([]);
      });
    return () => { cancelled = true; };
  }, [code]);

  const crumbs = [
    { to: '/', label: 'Home' },
    { to: '/services', label: 'Services' },
    { label: code },
  ];

  return (
    <Layout crumbs={crumbs}>
      <ErrorBanner message={error} />

      {!service && !error && <Loading label="서비스 정보 조회 중..." />}

      {service && (
        <div className="card">
          <h2>{service.display_name}</h2>
          <dl className="kv">
            <dt>서비스 코드</dt><dd><code>{service.code}</code></dd>
            <dt>게이트웨이</dt>
            <dd>
              {service.gateway_url
                ? <a href={service.gateway_url} target="_blank" rel="noreferrer">{service.gateway_url}</a>
                : <span className="muted">—</span>}
            </dd>
            <dt>레포</dt>
            <dd>
              {service.repo_url
                ? <a href={service.repo_url} target="_blank" rel="noreferrer">{service.repo_url}</a>
                : <span className="muted">—</span>}
            </dd>
            <dt>섹션 수</dt><dd>{service.section_count}</dd>
            <dt>상태</dt><dd><Tag kind="status" value={service.status} /></dd>
            <dt>최근 동기화</dt>
            <dd className="muted">
              {service.last_synced_at
                ? new Date(service.last_synced_at).toLocaleString('ko-KR')
                : '—'}
            </dd>
          </dl>
        </div>
      )}

      {sections && sections.length === 0 && !error && (
        <Empty>섹션이 없습니다.</Empty>
      )}

      {sections && sections.length > 0 && (
        <div className="card" style={{ padding: 0 }}>
          <table>
            <thead>
              <tr>
                <th style={{ width: 36 }}></th>
                <th style={{ width: 180 }}>섹션 코드</th>
                <th>표시명</th>
                <th style={{ width: 90 }}>레벨</th>
                <th style={{ width: 90 }}>상태</th>
                <th style={{ width: 220 }}>담당자</th>
                <th style={{ width: 90 }}>자산</th>
                <th style={{ width: 200 }}>헬스</th>
              </tr>
            </thead>
            <tbody>
              {sections.map((sec) => (
                <tr key={sec.id}>
                  <td><HealthDot summary={sec.health} /></td>
                  <td>
                    <Link to={`/services/${code}/sections/${sec.code}`}>
                      <code>{sec.code}</code>
                    </Link>
                  </td>
                  <td>{sec.name}</td>
                  <td><Tag kind="level" value={sec.level} /></td>
                  <td><Tag kind="status" value={sec.status} /></td>
                  <td className="muted">{sec.owner_email || '—'}</td>
                  <td>{sec.assets?.length ?? 0}</td>
                  <td><HealthDot summary={sec.health} withLabel /></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </Layout>
  );
}
