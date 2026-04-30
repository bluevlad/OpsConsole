import { useEffect, useState } from 'react';
import { Link, useParams } from 'react-router-dom';
import { getChangeRequest, patchChangeRequest } from '../api/catalog.js';
import { useAuth } from '../auth/AuthContext.jsx';
import { ErrorBanner, Layout, Loading } from '../components/Layout.jsx';

const STATUSES = ['submitted', 'in_pr', 'merged', 'closed', 'rejected'];

export default function ChangeRequestDetailPage() {
  const { id } = useParams();
  const { user } = useAuth();
  const [cr, setCr] = useState(null);
  const [error, setError] = useState(null);
  const [updating, setUpdating] = useState(false);

  async function refresh() {
    try {
      setError(null);
      const data = await getChangeRequest(id);
      setCr(data);
    } catch (err) {
      const msg = err.response?.data?.detail || err.message || '조회 실패';
      setError(msg);
    }
  }

  useEffect(() => { refresh(); }, [id]);

  async function setStatus(newStatus) {
    if (!confirm(`status 를 '${newStatus}' 로 변경할까요?`)) return;
    setUpdating(true);
    try {
      const data = await patchChangeRequest(id, { status: newStatus });
      setCr(data);
    } catch (err) {
      const msg = err.response?.data?.detail || err.message || '변경 실패';
      setError(msg);
    } finally {
      setUpdating(false);
    }
  }

  return (
    <Layout crumbs={[{ to: '/', label: 'Home' }, { to: '/my/change-requests', label: '내 변경요청' }, { label: `#${id}` }]}>
      <ErrorBanner message={error} />
      {!cr && !error && <Loading label="조회 중..." />}

      {cr && (
        <>
          <div className="card">
            <h2>{cr.title}</h2>
            <div style={{ marginBottom: 12 }}>
              <span className={`tag cr-${cr.status}`}>{cr.status}</span>{' '}
              <span className={`tag pri-${cr.priority}`}>{cr.priority}</span>
            </div>
            <dl className="kv">
              <dt>요청자</dt><dd>{cr.requester_email}</dd>
              {cr.section_code && (
                <>
                  <dt>섹션</dt>
                  <dd>
                    <Link to={`/services/${cr.service_code}/sections/${cr.section_code}`}>
                      <code>{cr.service_code}/{cr.section_code}</code>
                    </Link>
                  </dd>
                </>
              )}
              <dt>GitHub Issue</dt>
              <dd>
                {cr.github_issue_number ? (
                  <a href={cr.github_issue_url} target="_blank" rel="noreferrer">
                    #{cr.github_issue_number}
                  </a>
                ) : <span className="muted">미발급</span>}
              </dd>
              <dt>GitHub PR</dt>
              <dd>
                {cr.github_pr_number ? (
                  <a href={cr.github_pr_url} target="_blank" rel="noreferrer">
                    PR #{cr.github_pr_number}
                  </a>
                ) : <span className="muted">아직 없음</span>}
              </dd>
              <dt>생성</dt><dd className="muted">{new Date(cr.created_at).toLocaleString('ko-KR')}</dd>
              <dt>수정</dt><dd className="muted">{new Date(cr.updated_at).toLocaleString('ko-KR')}</dd>
              {cr.closed_at && (<><dt>종료</dt><dd className="muted">{new Date(cr.closed_at).toLocaleString('ko-KR')}</dd></>)}
            </dl>

            {user?.role === 'ops_admin' && (
              <div className="action-bar" style={{ marginTop: 16 }}>
                <span className="muted" style={{ fontSize: 12 }}>관리자 상태 전이:</span>
                {STATUSES.map((s) => (
                  <button
                    key={s}
                    className="btn"
                    disabled={updating || cr.status === s}
                    onClick={() => setStatus(s)}
                  >
                    {s}
                  </button>
                ))}
              </div>
            )}
          </div>

          <div className="card">
            <h2>본문</h2>
            {cr.description_md ? (
              <pre style={{ whiteSpace: 'pre-wrap', fontFamily: 'inherit', margin: 0, fontSize: 13.5 }}>
                {cr.description_md}
              </pre>
            ) : (
              <p className="muted" style={{ margin: 0 }}>본문 없음</p>
            )}
          </div>

          {cr.attachments && cr.attachments.length > 0 && (
            <div className="card">
              <h2>첨부 ({cr.attachments.length})</h2>
              <ul style={{ margin: 0, paddingLeft: 20 }}>
                {cr.attachments.map((a, i) => (
                  <li key={i}>
                    {a.url ? <a href={a.url} target="_blank" rel="noreferrer">{a.filename}</a> : a.filename}
                    {a.size && <span className="muted"> ({a.size} bytes)</span>}
                  </li>
                ))}
              </ul>
            </div>
          )}
        </>
      )}
    </Layout>
  );
}
