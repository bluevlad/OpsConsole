import { useEffect, useState } from 'react';
import { Link, useParams } from 'react-router-dom';
import {
  approveBlock,
  listSectionBlocks,
  publishBlock,
  rejectBlock,
  requestReview,
  saveDraft,
} from '../api/catalog.js';
import { useAuth } from '../auth/AuthContext.jsx';
import { Empty, ErrorBanner, Layout, Loading } from '../components/Layout.jsx';
import { MarkdownPreview } from '../components/Markdown.jsx';

export default function SectionContentPage() {
  const { code, section } = useParams();
  const { user } = useAuth();
  const [items, setItems] = useState(null);
  const [error, setError] = useState(null);

  async function refresh() {
    try {
      setError(null);
      const data = await listSectionBlocks(code, section);
      setItems(data);
    } catch (err) {
      const msg = err.response?.data?.detail || err.message || '목록 조회 실패';
      setError(msg);
      setItems([]);
    }
  }

  useEffect(() => { refresh(); }, [code, section]);

  const crumbs = [
    { to: '/', label: 'Home' },
    { to: '/services', label: 'Services' },
    { to: `/services/${code}/sections`, label: code },
    { to: `/services/${code}/sections/${section}`, label: section },
    { label: '콘텐츠' },
  ];

  return (
    <Layout crumbs={crumbs}>
      <ErrorBanner message={error} />
      {items === null && !error && <Loading label="콘텐츠 블록 조회 중..." />}
      {items && items.length === 0 && (
        <Empty>
          이 섹션에 등록된 콘텐츠 블록이 없습니다.
          <br />
          매니페스트의 <code>content_blocks</code> 화이트리스트에 추가 후{' '}
          <code>POST /api/catalog/sync</code> 하세요.
        </Empty>
      )}
      {items && items.length > 0 && items.map((item) => (
        <BlockEditor
          key={item.spec.key}
          serviceCode={code}
          sectionCode={section}
          item={item}
          user={user}
          onChanged={refresh}
        />
      ))}
    </Layout>
  );
}

function BlockEditor({ serviceCode, sectionCode, item, user, onChanged }) {
  const { spec, block } = item;
  const [draft, setDraft] = useState(block?.draft_body ?? '');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);

  // block 갱신 시 로컬 draft 동기화
  useEffect(() => { setDraft(block?.draft_body ?? ''); }, [block?.id, block?.draft_body, block?.published_version]);

  const status = block?.status ?? 'draft';
  const isAdmin = user?.role === 'ops_admin';
  // 권한 정보는 별도 API 가 없으므로 ops_admin 또는 (block 있고 user.role member 도) 시도해보고 403 시 안내
  const canTry = true;

  async function onSaveDraft() {
    setBusy(true); setError(null);
    try {
      await saveDraft(serviceCode, sectionCode, spec.key, draft);
      await onChanged();
    } catch (err) {
      setError(err.response?.data?.detail || err.message);
    } finally { setBusy(false); }
  }

  async function onRequestReview() {
    if (!block) return;
    setBusy(true); setError(null);
    try {
      await requestReview(block.id);
      await onChanged();
    } catch (err) {
      setError(err.response?.data?.detail || err.message);
    } finally { setBusy(false); }
  }

  async function onApprove() {
    if (!block) return;
    const note = prompt('승인 코멘트 (선택)') ?? null;
    setBusy(true); setError(null);
    try {
      await approveBlock(block.id, note);
      await onChanged();
    } catch (err) {
      setError(err.response?.data?.detail || err.message);
    } finally { setBusy(false); }
  }

  async function onReject() {
    if (!block) return;
    const note = prompt('반려 사유') ?? '';
    if (!note) return;
    setBusy(true); setError(null);
    try {
      await rejectBlock(block.id, note);
      await onChanged();
    } catch (err) {
      setError(err.response?.data?.detail || err.message);
    } finally { setBusy(false); }
  }

  async function onPublishDirect() {
    if (!block) return;
    if (!confirm('검토 단계 없이 즉시 게시합니다. 계속할까요?')) return;
    setBusy(true); setError(null);
    try {
      await publishBlock(block.id);
      await onChanged();
    } catch (err) {
      setError(err.response?.data?.detail || err.message);
    } finally { setBusy(false); }
  }

  return (
    <div className="card">
      <div style={{ display: 'flex', alignItems: 'baseline', gap: 12, marginBottom: 6 }}>
        <h2 style={{ margin: 0 }}><code>{spec.key}</code></h2>
        <span className={`tag cb-${status}`}>{status}</span>
        {block && block.published_version > 0 && (
          <span className="tag" style={{ fontSize: 11 }}>v{block.published_version}</span>
        )}
        <span className="muted" style={{ marginLeft: 'auto', fontSize: 12 }}>
          {spec.format} · max {spec.max_length} · locales: {spec.locales.join(', ')}
        </span>
      </div>
      {spec.description && <p className="muted" style={{ marginTop: 0, fontSize: 12 }}>{spec.description}</p>}

      <ErrorBanner message={error} />

      <div className="editor-row">
        <div>
          <div className="muted" style={{ fontSize: 12, marginBottom: 4 }}>편집 ({draft.length} / {spec.max_length})</div>
          <textarea
            className="cr-md"
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
            disabled={busy}
          />
        </div>
        <div>
          <div className="muted" style={{ fontSize: 12, marginBottom: 4 }}>미리보기</div>
          <div style={{ background: 'var(--panel-2)', border: '1px solid var(--border)', borderRadius: 6, padding: '10px 12px', minHeight: 180 }}>
            <MarkdownPreview body={draft} format={spec.format} />
          </div>
        </div>
      </div>

      <div className="action-bar" style={{ flexWrap: 'wrap' }}>
        <button className="btn primary" disabled={busy || draft === (block?.draft_body ?? '')} onClick={onSaveDraft}>
          {busy ? <span className="spinner" /> : null}draft 저장
        </button>
        <button className="btn" disabled={busy || !block || status === 'pending_review'} onClick={onRequestReview}>
          검토 요청
        </button>
        {block && status === 'pending_review' && (
          <>
            <button className="btn primary" disabled={busy} onClick={onApprove}>승인 + 게시</button>
            <button className="btn" disabled={busy} onClick={onReject}>반려</button>
          </>
        )}
        {isAdmin && block && (
          <button className="btn" disabled={busy || draft.length === 0} onClick={onPublishDirect} style={{ marginLeft: 'auto' }}>
            ⚡ 즉시 게시 (admin)
          </button>
        )}
      </div>

      {block?.published_body && (
        <div style={{ marginTop: 14, paddingTop: 14, borderTop: '1px solid var(--border)' }}>
          <div className="muted" style={{ fontSize: 12 }}>
            현재 게시본 (v{block.published_version})
            {block.published_at && ` · ${new Date(block.published_at).toLocaleString('ko-KR')}`}
          </div>
          <div style={{ marginTop: 8, fontSize: 12, color: 'var(--muted)' }}>
            <Link to={`/services/${serviceCode}/sections/${sectionCode}`}>← 섹션 상세로</Link>
          </div>
        </div>
      )}
    </div>
  );
}
