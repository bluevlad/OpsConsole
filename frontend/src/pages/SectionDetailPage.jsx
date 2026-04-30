import { useEffect, useState } from 'react';
import { Link, useParams } from 'react-router-dom';
import { ErrorBanner, Layout, Loading, Tag } from '../components/Layout.jsx';
import { HealthSummaryCard } from '../components/Health.jsx';
import { getSection, getService } from '../api/catalog.js';
import { useAuth } from '../auth/AuthContext.jsx';

const ASSET_TYPE_ORDER = ['frontend', 'backend_router', 'service', 'model', 'table', 'endpoint'];

function groupAssets(assets) {
  const groups = {};
  for (const a of assets || []) {
    if (!groups[a.asset_type]) groups[a.asset_type] = [];
    groups[a.asset_type].push(a);
  }
  return ASSET_TYPE_ORDER
    .filter((t) => groups[t]?.length)
    .map((t) => ({ type: t, items: groups[t] }))
    .concat(
      Object.keys(groups)
        .filter((t) => !ASSET_TYPE_ORDER.includes(t))
        .map((t) => ({ type: t, items: groups[t] })),
    );
}

export default function SectionDetailPage() {
  const { code, section } = useParams();
  const { user } = useAuth();
  const [service, setService] = useState(null);
  const [data, setData] = useState(null);
  const [error, setError] = useState(null);

  useEffect(() => {
    let cancelled = false;
    Promise.all([getService(code), getSection(code, section)])
      .then(([svc, sec]) => {
        if (cancelled) return;
        setService(svc);
        setData(sec);
      })
      .catch((err) => {
        if (cancelled) return;
        const msg = err.response?.data?.detail || err.message || '섹션 상세 조회 실패';
        setError(msg);
      });
    return () => { cancelled = true; };
  }, [code, section]);

  const crumbs = [
    { to: '/', label: 'Home' },
    { to: '/services', label: 'Services' },
    { to: `/services/${code}/sections`, label: code },
    { label: section },
  ];

  return (
    <Layout crumbs={crumbs}>
      <ErrorBanner message={error} />
      {!data && !error && <Loading label="섹션 상세 조회 중..." />}

      {data && (
        <>
          <div className="card">
            <h2>{data.name}</h2>
            <div style={{ marginBottom: 12 }}>
              <Tag kind="level" value={data.level} />{' '}
              <Tag kind="status" value={data.status} />
            </div>
            <dl className="kv">
              <dt>섹션 코드</dt><dd><code>{data.code}</code></dd>
              <dt>라우트</dt>
              <dd>
                {data.route
                  ? <code>{data.route}</code>
                  : <span className="muted">—</span>}
              </dd>
              <dt>1차 담당자</dt>
              <dd>{data.owner_email || <span className="muted">—</span>}</dd>
              <dt>예비 담당자</dt>
              <dd>{data.backup_email || <span className="muted">—</span>}</dd>
              {service?.gateway_url && data.route && (
                <>
                  <dt>게이트웨이 링크</dt>
                  <dd>
                    <a
                      href={`${service.gateway_url.replace(/\/$/, '')}${data.route}`}
                      target="_blank"
                      rel="noreferrer"
                    >
                      {service.gateway_url.replace(/\/$/, '') + data.route}
                    </a>
                  </dd>
                </>
              )}
            </dl>
          </div>

          <HealthSummaryCard summary={data.health} />

          {user?.role === 'ops_admin' && (
            <div className="card">
              <h2>권한 (ops_admin)</h2>
              <p className="muted" style={{ margin: 0 }}>
                <Link to={`/services/${code}/sections/${section}/permissions`}>
                  → 권한 부여/해제
                </Link>
              </p>
            </div>
          )}

          <div className="card">
            <h2>자산 ({data.assets?.length || 0})</h2>
            {!data.assets || data.assets.length === 0 ? (
              <p className="muted" style={{ margin: 0 }}>등록된 자산이 없습니다.</p>
            ) : (
              groupAssets(data.assets).map((g) => (
                <div key={g.type} style={{ marginTop: 8 }}>
                  <div className="muted" style={{ fontSize: 12, fontWeight: 600, textTransform: 'uppercase', letterSpacing: 0.5 }}>
                    {g.type} ({g.items.length})
                  </div>
                  <ul className="assets-list">
                    {g.items.map((a, i) => (
                      <li key={i}>
                        <code>{a.path}</code>
                        {a.notes && <span className="muted"> — {a.notes}</span>}
                      </li>
                    ))}
                  </ul>
                </div>
              ))
            )}
          </div>
        </>
      )}
    </Layout>
  );
}
