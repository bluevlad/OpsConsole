import { useEffect, useState } from 'react';
import { cmd } from '../api/tauri.js';

function dotClass(h) {
  if (!h || h.last_ok === null) return '';
  if (!h.last_ok) return 'err';
  if (h.availability_24h !== null && h.availability_24h < 0.95) return 'warn';
  return 'ok';
}

export default function MySectionsPanel() {
  const [rows, setRows] = useState(null);
  const [error, setError] = useState(null);

  async function refresh() {
    try {
      setError(null);
      const data = await cmd.fetchMySections();
      setRows(data);
    } catch (err) {
      setError(String(err));
      setRows([]);
    }
  }
  useEffect(() => { refresh(); }, []);

  return (
    <div>
      <div className="row" style={{ marginBottom: 8 }}>
        <strong>내 섹션</strong>
        <button className="btn" style={{ marginLeft: 'auto', fontSize: 11 }} onClick={refresh}>새로고침</button>
      </div>
      {error && <div className="error">{error}</div>}
      {rows === null && <div className="muted">조회 중...</div>}
      {rows && rows.length === 0 && (
        <div className="muted">담당하는 섹션이 없습니다.</div>
      )}
      {rows && rows.length > 0 && rows.map((r) => (
        <div key={r.section_id} className="card">
          <div className="row">
            <span className={`dot ${dotClass(r.health)}`} />
            <strong style={{ fontSize: 13 }}>{r.section_name}</strong>
            <span className="muted" style={{ fontSize: 11, marginLeft: 'auto' }}>{r.relation}</span>
          </div>
          <div className="muted" style={{ fontSize: 11.5, marginTop: 2 }}>
            {r.service_code} / {r.section_code}
            {r.health?.last_status && ` · ${r.health.last_status}`}
            {r.health?.last_latency_ms && ` · ${r.health.last_latency_ms}ms`}
            {r.health?.samples_24h > 0 && ` · 24h ${(r.health.availability_24h * 100).toFixed(1)}%`}
          </div>
          <div style={{ marginTop: 6 }}>
            <button
              className="btn"
              style={{ fontSize: 11 }}
              onClick={() => cmd.openExternal(`https://opsconsole.unmong.com/services/${r.service_code}/sections/${r.section_code}`)}
            >
              웹에서 열기
            </button>
          </div>
        </div>
      ))}
    </div>
  );
}
