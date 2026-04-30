/**
 * 헬스 요약 표시. summary 모양:
 *  { last_ok, last_status, last_latency_ms, last_checked_at, availability_24h, samples_24h }
 */

function dotClass(summary) {
  if (!summary || summary.last_ok === null || summary.last_ok === undefined) return 'unknown';
  if (summary.last_ok) {
    if (summary.availability_24h !== null && summary.availability_24h < 0.95) return 'warn';
    return 'ok';
  }
  return 'err';
}

function fmtPct(n) {
  if (n === null || n === undefined) return '—';
  return `${(n * 100).toFixed(1)}%`;
}

function fmtMs(n) {
  if (n === null || n === undefined) return '—';
  return `${n}ms`;
}

export function HealthDot({ summary, withLabel = false }) {
  const cls = dotClass(summary);
  if (!withLabel) return <span className={`dot ${cls}`} title={summary?.last_status ?? 'unknown'} />;

  const status = summary?.last_status;
  return (
    <span>
      <span className={`dot ${cls}`} />
      <span className="health-text">
        {status ? <strong>{status}</strong> : '—'}{' '}
        {summary?.last_latency_ms != null && <>· {fmtMs(summary.last_latency_ms)}</>}{' '}
        {summary?.samples_24h > 0 && (
          <> · 24h {fmtPct(summary.availability_24h)} ({summary.samples_24h})</>
        )}
      </span>
    </span>
  );
}

export function HealthSummaryCard({ summary }) {
  if (!summary) return null;
  return (
    <div className="card">
      <h2>헬스 (P1)</h2>
      <dl className="kv">
        <dt>최근 상태</dt>
        <dd><HealthDot summary={summary} withLabel /></dd>
        <dt>마지막 점검</dt>
        <dd className="muted">
          {summary.last_checked_at
            ? new Date(summary.last_checked_at).toLocaleString('ko-KR')
            : '—'}
        </dd>
        <dt>24시간 가용률</dt>
        <dd>
          {summary.samples_24h > 0
            ? `${fmtPct(summary.availability_24h)} (samples ${summary.samples_24h})`
            : <span className="muted">시계열 미수집</span>}
        </dd>
      </dl>
    </div>
  );
}
