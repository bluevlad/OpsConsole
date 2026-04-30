import { useEffect, useState } from 'react';
import { useParams } from 'react-router-dom';
import {
  createOrUpdateAssignment,
  getSection,
  listAssignments,
  revokeAssignment,
} from '../api/catalog.js';
import { Empty, ErrorBanner, Layout, Loading } from '../components/Layout.jsx';

export default function PermissionsPage() {
  const { code, section: sectionCode } = useParams();
  const [section, setSection] = useState(null);
  const [rows, setRows] = useState(null);
  const [error, setError] = useState(null);

  const [email, setEmail] = useState('');
  const [canEdit, setCanEdit] = useState(false);
  const [canPR, setCanPR] = useState(true);
  const [canPub, setCanPub] = useState(false);
  const [submitting, setSubmitting] = useState(false);

  async function refresh() {
    try {
      setError(null);
      const sec = await getSection(code, sectionCode);
      const list = await listAssignments(sec.id);
      setSection(sec);
      setRows(list);
    } catch (err) {
      const msg = err.response?.data?.detail || err.message || '권한 조회 실패';
      setError(msg);
      setRows([]);
    }
  }

  useEffect(() => { refresh(); }, [code, sectionCode]);

  async function onSubmit(e) {
    e.preventDefault();
    if (!section) return;
    setSubmitting(true);
    setError(null);
    try {
      await createOrUpdateAssignment({
        section_id: section.id,
        user_email: email.trim(),
        can_edit_content: canEdit,
        can_open_pr: canPR,
        can_publish: canPub,
      });
      setEmail('');
      await refresh();
    } catch (err) {
      const msg = err.response?.data?.detail || err.message || '권한 부여 실패';
      setError(msg);
    } finally {
      setSubmitting(false);
    }
  }

  async function onRevoke(id) {
    if (!confirm('이 권한을 해제할까요?')) return;
    try {
      await revokeAssignment(id);
      await refresh();
    } catch (err) {
      const msg = err.response?.data?.detail || err.message || '권한 해제 실패';
      setError(msg);
    }
  }

  const crumbs = [
    { to: '/', label: 'Home' },
    { to: '/services', label: 'Services' },
    { to: `/services/${code}/sections`, label: code },
    { to: `/services/${code}/sections/${sectionCode}`, label: sectionCode },
    { label: '권한' },
  ];

  return (
    <Layout crumbs={crumbs}>
      <ErrorBanner message={error} />

      {section === null && !error && <Loading label="섹션 조회 중..." />}

      {section && (
        <>
          <div className="card">
            <h2>권한 부여 — <code>{section.code}</code> · {section.name}</h2>
            <form onSubmit={onSubmit}>
              <div className="kv" style={{ gridTemplateColumns: '140px 1fr' }}>
                <label>사용자 이메일</label>
                <div>
                  <input
                    type="email"
                    required
                    value={email}
                    onChange={(e) => setEmail(e.target.value)}
                    placeholder="user@example.com"
                    style={{ width: '100%', padding: '6px 10px', background: 'var(--code-bg)', color: 'var(--text)', border: '1px solid var(--border)', borderRadius: 6 }}
                  />
                  <div className="muted" style={{ fontSize: 11.5, marginTop: 4 }}>
                    OpsConsole 에 처음 등록되는 이메일이면 placeholder 계정이 생성됩니다.
                  </div>
                </div>
                <label>can_edit_content</label>
                <div>
                  <label><input type="checkbox" checked={canEdit} onChange={(e) => setCanEdit(e.target.checked)} /> 콘텐츠 블록 편집 (P3)</label>
                </div>
                <label>can_open_pr</label>
                <div>
                  <label><input type="checkbox" checked={canPR} onChange={(e) => setCanPR(e.target.checked)} /> 변경요청 PR 발급 (P2)</label>
                </div>
                <label>can_publish</label>
                <div>
                  <label><input type="checkbox" checked={canPub} onChange={(e) => setCanPub(e.target.checked)} /> 콘텐츠 게시 승인 (P3)</label>
                </div>
              </div>
              <div style={{ marginTop: 12 }}>
                <button className="btn primary" type="submit" disabled={submitting}>
                  {submitting ? <span className="spinner" /> : null}부여 / 갱신
                </button>
              </div>
            </form>
          </div>

          <div className="card" style={{ padding: 0 }}>
            {rows && rows.length === 0 ? (
              <Empty>아직 부여된 권한이 없습니다.</Empty>
            ) : rows ? (
              <table>
                <thead>
                  <tr>
                    <th>사용자</th>
                    <th style={{ width: 120, textAlign: 'center' }}>edit</th>
                    <th style={{ width: 120, textAlign: 'center' }}>open_pr</th>
                    <th style={{ width: 120, textAlign: 'center' }}>publish</th>
                    <th>granted_at</th>
                    <th style={{ width: 80 }}></th>
                  </tr>
                </thead>
                <tbody>
                  {rows.map((r) => (
                    <tr key={r.id}>
                      <td>
                        <div>{r.user_email}</div>
                        {r.user_name && <div className="muted" style={{ fontSize: 11.5 }}>{r.user_name}</div>}
                      </td>
                      <td style={{ textAlign: 'center' }}>{r.can_edit_content ? '✓' : ''}</td>
                      <td style={{ textAlign: 'center' }}>{r.can_open_pr ? '✓' : ''}</td>
                      <td style={{ textAlign: 'center' }}>{r.can_publish ? '✓' : ''}</td>
                      <td className="muted">{new Date(r.granted_at).toLocaleString('ko-KR')}</td>
                      <td><button className="btn" onClick={() => onRevoke(r.id)}>해제</button></td>
                    </tr>
                  ))}
                </tbody>
              </table>
            ) : (
              <Loading label="권한 조회 중..." />
            )}
          </div>
        </>
      )}
    </Layout>
  );
}
