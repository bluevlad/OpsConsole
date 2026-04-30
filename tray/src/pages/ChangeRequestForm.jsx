import { useState } from 'react';
import { cmd } from '../api/tauri.js';

/**
 * 트레이 변경요청 폼 — 백엔드 POST /api/change-requests 직접 호출.
 * 토큰은 Rust 측에서 keychain → bearer 주입.
 */
export default function ChangeRequestForm() {
  const [title, setTitle] = useState('');
  const [desc, setDesc] = useState('');
  const [priority, setPriority] = useState('normal');
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState(null);
  const [error, setError] = useState(null);

  async function submit(e) {
    e.preventDefault();
    setBusy(true); setError(null); setResult(null);
    try {
      // 트레이 → Rust → REST. 본 폼은 section_id 미지정 (전역 변경요청).
      // section 지정은 웹에서 진행 권장 (UI 제약).
      const token = await cmd.loadToken();
      const res = await fetch('https://opsconsole.unmong.com/api/change-requests', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` },
        body: JSON.stringify({
          title: title.trim(),
          description_md: desc || null,
          priority,
          skip_github: true,  // 트레이는 일단 skip — GitHub 연동은 웹에서 (PAT 정책상)
        }),
      });
      if (!res.ok) {
        const body = await res.json().catch(() => ({}));
        throw new Error(body.detail || `HTTP ${res.status}`);
      }
      const cr = await res.json();
      setResult(cr);
      setTitle(''); setDesc('');
    } catch (err) {
      setError(String(err));
    } finally {
      setBusy(false);
    }
  }

  return (
    <form onSubmit={submit}>
      <div className="row" style={{ marginBottom: 8 }}>
        <strong>변경요청 (빠른 작성)</strong>
      </div>
      {error && <div className="error">{error}</div>}
      {result && (
        <div className="card" style={{ background: 'rgba(62,199,141,0.1)', borderColor: 'rgba(62,199,141,0.4)' }}>
          ✅ #{result.id} 등록됨 — 웹에서 GitHub 연동·섹션 지정 가능
        </div>
      )}

      <label className="muted" style={{ fontSize: 12 }}>제목</label>
      <input value={title} onChange={(e) => setTitle(e.target.value)} maxLength={200} required />
      <div style={{ height: 8 }} />
      <label className="muted" style={{ fontSize: 12 }}>본문 (Markdown)</label>
      <textarea value={desc} onChange={(e) => setDesc(e.target.value)} placeholder="상세 설명..." />
      <div style={{ height: 8 }} />
      <div className="row">
        <label className="muted" style={{ fontSize: 12 }}>우선순위</label>
        <select value={priority} onChange={(e) => setPriority(e.target.value)}>
          <option value="low">low</option>
          <option value="normal">normal</option>
          <option value="high">high</option>
          <option value="urgent">urgent</option>
        </select>
        <button type="submit" className="btn primary" disabled={busy || !title} style={{ marginLeft: 'auto' }}>
          {busy ? '...' : '제출'}
        </button>
      </div>
      <p className="muted" style={{ fontSize: 11, marginTop: 8 }}>
        섹션 지정 / GitHub Issue 발급은 웹에서 진행하세요.
      </p>
    </form>
  );
}
