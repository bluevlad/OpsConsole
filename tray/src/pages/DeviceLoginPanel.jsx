import { useEffect, useRef, useState } from 'react';
import { cmd } from '../api/tauri.js';

export default function DeviceLoginPanel({ onLogin }) {
  const [phase, setPhase] = useState('idle'); // idle / pending / success / expired / error
  const [data, setData] = useState(null);
  const [error, setError] = useState(null);
  const pollRef = useRef(null);

  useEffect(() => {
    return () => { if (pollRef.current) clearInterval(pollRef.current); };
  }, []);

  async function start() {
    setError(null); setPhase('pending');
    try {
      const init = await cmd.deviceInit();
      setData(init);
      // 브라우저로 승인 페이지 자동 오픈 (?code=... 자동 입력)
      cmd.openExternal(`${init.verification_uri}?code=${encodeURIComponent(init.user_code)}`);
      // 폴링 시작
      pollRef.current = setInterval(async () => {
        try {
          const res = await cmd.devicePoll(init.device_code);
          if (res.status === 'approved') {
            clearInterval(pollRef.current);
            await cmd.saveToken(res.access_token);
            setPhase('success');
            onLogin?.(res.access_token);
          } else if (res.status === 'expired') {
            clearInterval(pollRef.current);
            setPhase('expired');
          }
        } catch (err) {
          clearInterval(pollRef.current);
          setError(String(err));
          setPhase('error');
        }
      }, init.interval * 1000);
    } catch (err) {
      setError(String(err));
      setPhase('error');
    }
  }

  return (
    <div>
      <h3 style={{ marginTop: 0 }}>디바이스 로그인</h3>
      <p className="muted" style={{ fontSize: 12, marginTop: 0 }}>
        OpsConsole 웹에 이미 로그인된 브라우저로 아래 코드를 승인하면 데스크톱 앱이 자동으로 인증을 마칩니다.
      </p>

      {error && <div className="error">{error}</div>}

      {phase === 'idle' && (
        <button className="btn primary" onClick={start}>로그인 시작</button>
      )}

      {phase === 'pending' && data && (
        <>
          <div className="muted" style={{ fontSize: 12 }}>이 코드를 브라우저에 입력하세요</div>
          <div className="code-display">{data.user_code}</div>
          <p className="muted" style={{ fontSize: 12 }}>
            {data.verification_uri} 으로 자동 이동했습니다. 안 열렸다면 직접 열어주세요.
          </p>
          <p className="muted" style={{ fontSize: 12 }}>
            {data.interval}초 마다 폴링 중. {data.expires_in}초 안에 승인하세요.
          </p>
        </>
      )}

      {phase === 'success' && (
        <div style={{ color: 'var(--ok)' }}>✅ 로그인 성공</div>
      )}

      {phase === 'expired' && (
        <>
          <div style={{ color: 'var(--warn)' }}>코드가 만료되었습니다.</div>
          <button className="btn primary" onClick={start} style={{ marginTop: 8 }}>다시 시도</button>
        </>
      )}

      {phase === 'error' && (
        <button className="btn primary" onClick={start} style={{ marginTop: 8 }}>다시 시도</button>
      )}
    </div>
  );
}
