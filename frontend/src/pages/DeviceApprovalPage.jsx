import { useEffect, useState } from 'react';
import { useSearchParams } from 'react-router-dom';
import { approveDeviceCode, lookupDeviceCode } from '../api/catalog.js';
import { useAuth } from '../auth/AuthContext.jsx';
import { ErrorBanner, Layout, Loading } from '../components/Layout.jsx';

const NORMALIZE = (s) => s.toUpperCase().replace(/[^A-Z0-9]/g, '');

function formatUserCode(s) {
  const n = NORMALIZE(s);
  return n.length > 4 ? `${n.slice(0, 4)}-${n.slice(4, 8)}` : n;
}

export default function DeviceApprovalPage() {
  const [params] = useSearchParams();
  const { user } = useAuth();
  const [code, setCode] = useState(params.get('code') || '');
  const [meta, setMeta] = useState(null);
  const [error, setError] = useState(null);
  const [busy, setBusy] = useState(false);
  const [done, setDone] = useState(false);

  // 자동 lookup if URL ?code=... + 로그인 됨
  useEffect(() => {
    const initial = params.get('code');
    if (initial && user) {
      onLookup(initial);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [user]);

  async function onLookup(c = code) {
    const formatted = formatUserCode(c);
    setError(null);
    setMeta(null);
    if (formatted.length < 9) {
      setError('사용자 코드는 8자 (XXXX-XXXX) 입니다');
      return;
    }
    setBusy(true);
    try {
      const data = await lookupDeviceCode(formatted);
      setMeta(data);
      setCode(formatted);
    } catch (err) {
      setError(err.response?.data?.detail || err.message);
    } finally {
      setBusy(false);
    }
  }

  async function onApprove() {
    if (!meta) return;
    setBusy(true); setError(null);
    try {
      await approveDeviceCode(meta.user_code);
      setDone(true);
    } catch (err) {
      setError(err.response?.data?.detail || err.message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <Layout crumbs={[{ to: '/', label: 'Home' }, { label: '디바이스 승인' }]}>
      <ErrorBanner message={error} />

      <div className="card" style={{ maxWidth: 560 }}>
        <h2>디바이스 코드 승인</h2>
        <p className="muted" style={{ marginTop: 0, fontSize: 13 }}>
          OpsConsole 트레이 앱 등 데스크톱 클라이언트가 표시한 8자 코드를 입력하세요.
          확인 후 <code>승인</code> 하면 해당 디바이스가 본 계정으로 OpsConsole API를 호출할 수 있습니다.
        </p>

        {done ? (
          <div className="card" style={{ background: 'rgba(62,199,141,0.1)', borderColor: 'rgba(62,199,141,0.4)' }}>
            <h3 style={{ margin: 0 }}>✅ 승인 완료</h3>
            <p style={{ marginBottom: 0, fontSize: 13 }}>
              데스크톱 앱이 자동으로 인증을 마칩니다. 이 창은 닫으셔도 됩니다.
            </p>
          </div>
        ) : meta ? (
          <ApprovalConfirm meta={meta} onApprove={onApprove} busy={busy} />
        ) : (
          <CodeForm code={code} setCode={setCode} onLookup={() => onLookup()} busy={busy} />
        )}
      </div>
    </Layout>
  );
}

function CodeForm({ code, setCode, onLookup, busy }) {
  return (
    <form onSubmit={(e) => { e.preventDefault(); onLookup(); }} style={{ marginTop: 12 }}>
      <label className="muted" style={{ fontSize: 12 }}>사용자 코드</label>
      <input
        className="cr-text"
        style={{ fontFamily: 'ui-monospace, monospace', fontSize: 18, letterSpacing: 2, textAlign: 'center', textTransform: 'uppercase' }}
        value={code}
        onChange={(e) => setCode(formatUserCode(e.target.value))}
        placeholder="XXXX-XXXX"
        maxLength={9}
        autoFocus
      />
      <div style={{ marginTop: 12 }}>
        <button className="btn primary" type="submit" disabled={busy || code.length < 9}>
          {busy ? <span className="spinner" /> : null}확인
        </button>
      </div>
    </form>
  );
}

function ApprovalConfirm({ meta, onApprove, busy }) {
  return (
    <div style={{ marginTop: 12 }}>
      <dl className="kv">
        <dt>사용자 코드</dt><dd><code>{meta.user_code}</code></dd>
        <dt>디바이스</dt><dd>{meta.device_label || <span className="muted">미명시</span>}</dd>
        <dt>User-Agent</dt><dd className="muted" style={{ fontSize: 12 }}>{meta.user_agent || '—'}</dd>
        <dt>만료</dt>
        <dd className="muted">{new Date(meta.expires_at).toLocaleString('ko-KR')}</dd>
      </dl>
      {meta.approved && (
        <p className="muted" style={{ fontSize: 13 }}>이미 승인된 코드입니다 (재승인 가능).</p>
      )}
      <button className="btn primary" disabled={busy} onClick={onApprove}>
        {busy ? <span className="spinner" /> : null}이 디바이스를 내 계정으로 승인
      </button>
    </div>
  );
}
