import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { listChangeRequests } from '../api/catalog.js';
import { Empty, ErrorBanner, Layout, Loading, Tag } from '../components/Layout.jsx';

export default function MyChangeRequestsPage() {
  const [rows, setRows] = useState(null);
  const [error, setError] = useState(null);
  const [statusFilter, setStatusFilter] = useState('');

  useEffect(() => {
    setRows(null);
    listChangeRequests({ mine: true, ...(statusFilter ? { status: statusFilter } : {}) })
      .then(setRows)
      .catch((err) => {
        const msg = err.response?.data?.detail || err.message || '조회 실패';
        setError(msg);
        setRows([]);
      });
  }, [statusFilter]);

  return (
    <Layout crumbs={[{ to: '/', label: 'Home' }, { label: '내 변경요청' }]}>
      <ErrorBanner message={error} />

      <div className="action-bar">
        <span className="muted" style={{ fontSize: 13 }}>내가 발급한 변경요청</span>
        <select className="cr-sel" value={statusFilter} onChange={(e) => setStatusFilter(e.target.value)} style={{ marginLeft: 8 }}>
          <option value="">전체</option>
          <option value="submitted">submitted</option>
          <option value="in_pr">in_pr</option>
          <option value="merged">merged</option>
          <option value="closed">closed</option>
          <option value="rejected">rejected</option>
        </select>
        <Link className="btn primary" to="/change-requests/new" style={{ marginLeft: 'auto' }}>
          + 새 변경요청
        </Link>
      </div>

      {rows === null && !error && <Loading label="조회 중..." />}
      {rows && rows.length === 0 && !error && (
        <Empty>발급한 변경요청이 없습니다.</Empty>
      )}
      {rows && rows.length > 0 && (
        <ChangeRequestsTable rows={rows} />
      )}
    </Layout>
  );
}

export function ChangeRequestsTable({ rows }) {
  return (
    <div className="card" style={{ padding: 0 }}>
      <table>
        <thead>
          <tr>
            <th style={{ width: 60 }}>#</th>
            <th>제목</th>
            <th style={{ width: 140 }}>섹션</th>
            <th style={{ width: 100 }}>우선순위</th>
            <th style={{ width: 110 }}>상태</th>
            <th style={{ width: 140 }}>GitHub</th>
            <th style={{ width: 160 }}>생성일</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((r) => (
            <tr key={r.id}>
              <td>{r.id}</td>
              <td>
                <Link to={`/change-requests/${r.id}`}>{r.title}</Link>
                {r.requester_email && (
                  <div className="muted" style={{ fontSize: 11.5 }}>by {r.requester_email}</div>
                )}
              </td>
              <td>
                {r.section_code ? (
                  <Link to={`/services/${r.service_code}/sections/${r.section_code}`}>
                    <code>{r.section_code}</code>
                  </Link>
                ) : (
                  <span className="muted">—</span>
                )}
              </td>
              <td><span className={`tag pri-${r.priority}`}>{r.priority}</span></td>
              <td><span className={`tag cr-${r.status}`}>{r.status}</span></td>
              <td>
                {r.github_issue_number ? (
                  <a href={r.github_issue_url} target="_blank" rel="noreferrer">#{r.github_issue_number}</a>
                ) : (
                  <span className="muted">—</span>
                )}
                {r.github_pr_number && (
                  <>
                    {' / '}
                    <a href={r.github_pr_url} target="_blank" rel="noreferrer">PR #{r.github_pr_number}</a>
                  </>
                )}
              </td>
              <td className="muted">{new Date(r.created_at).toLocaleString('ko-KR')}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
