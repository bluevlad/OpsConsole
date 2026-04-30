import { useEffect, useState } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { createChangeRequest, getSection } from '../api/catalog.js';
import { ErrorBanner, Layout } from '../components/Layout.jsx';

export default function ChangeRequestNewPage() {
  const [params] = useSearchParams();
  const nav = useNavigate();

  const serviceCode = params.get('service');
  const sectionCode = params.get('section');

  const [section, setSection] = useState(null);
  const [error, setError] = useState(null);
  const [submitting, setSubmitting] = useState(false);

  const [title, setTitle] = useState('');
  const [desc, setDesc] = useState('');
  const [priority, setPriority] = useState('normal');
  const [skipGithub, setSkipGithub] = useState(false);

  useEffect(() => {
    if (serviceCode && sectionCode) {
      getSection(serviceCode, sectionCode).then(setSection).catch(() => setSection(null));
    }
  }, [serviceCode, sectionCode]);

  async function onSubmit(e) {
    e.preventDefault();
    setSubmitting(true);
    setError(null);
    try {
      const cr = await createChangeRequest({
        section_id: section?.id ?? null,
        title: title.trim(),
        description_md: desc || null,
        priority,
        skip_github: skipGithub,
      });
      nav(`/my/change-requests`);
    } catch (err) {
      const msg = err.response?.data?.detail || err.message || '변경요청 생성 실패';
      setError(msg);
    } finally {
      setSubmitting(false);
    }
  }

  const crumbs = [{ to: '/', label: 'Home' }];
  if (serviceCode) crumbs.push({ to: '/services', label: 'Services' });
  if (serviceCode) crumbs.push({ to: `/services/${serviceCode}/sections`, label: serviceCode });
  if (sectionCode) crumbs.push({ to: `/services/${serviceCode}/sections/${sectionCode}`, label: sectionCode });
  crumbs.push({ label: '변경요청 작성' });

  return (
    <Layout crumbs={crumbs}>
      <ErrorBanner message={error} />

      <div className="card">
        <h2>변경요청 작성</h2>
        <p className="muted" style={{ marginTop: 0, fontSize: 13 }}>
          제출 시 OpsConsole 변경요청이 등록되고, 섹션이 지정되어 있고 백엔드 PAT 가 설정돼 있으면
          해당 서비스 GitHub 레포에 Issue 가 자동 생성됩니다.
        </p>

        {section && (
          <div className="kv" style={{ marginTop: 8 }}>
            <dt>대상 섹션</dt>
            <dd>
              <code>{section.code}</code> · {section.name} ({section.level})
            </dd>
          </div>
        )}

        <form onSubmit={onSubmit} style={{ marginTop: 16 }}>
          <div style={{ marginBottom: 12 }}>
            <label className="muted" style={{ fontSize: 12 }}>제목 *</label>
            <input
              required
              className="cr-text"
              maxLength={200}
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              placeholder="변경 요청 한 줄 요약"
            />
          </div>
          <div style={{ marginBottom: 12 }}>
            <label className="muted" style={{ fontSize: 12 }}>본문 (Markdown)</label>
            <textarea
              className="cr-md"
              value={desc}
              onChange={(e) => setDesc(e.target.value)}
              placeholder={"## 배경\n무엇을 왜 바꾸나요?\n\n## 변경 내용\n- 항목 1\n- 항목 2\n\n## 검증 방법\n"}
            />
          </div>
          <div className="action-bar" style={{ gap: 16 }}>
            <label className="muted" style={{ fontSize: 12 }}>우선순위</label>
            <select className="cr-sel" value={priority} onChange={(e) => setPriority(e.target.value)}>
              <option value="low">low</option>
              <option value="normal">normal</option>
              <option value="high">high</option>
              <option value="urgent">urgent</option>
            </select>
            <label style={{ fontSize: 13, marginLeft: 16 }}>
              <input type="checkbox" checked={skipGithub} onChange={(e) => setSkipGithub(e.target.checked)} />
              {' '}GitHub Issue 발급 생략
            </label>
            <button className="btn primary" disabled={submitting} type="submit" style={{ marginLeft: 'auto' }}>
              {submitting ? <span className="spinner" /> : null}변경요청 제출
            </button>
          </div>
        </form>
      </div>
    </Layout>
  );
}
